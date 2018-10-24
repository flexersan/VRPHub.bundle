# VRPHub
import re, types, traceback
import Queue

# URLS
VERSION_NO = '1.2016.06.30.1'
D18_BASE_URL = 'https://vrphub.com/'
D18_MOVIE_INFO = D18_BASE_URL + '/%s'
D18_SEARCH_URL = D18_BASE_URL + '?s=%s'
#D18_STAR_PHOTO = D18_BASE_URL + 'img/stars/120/%s.jpg'

REQUEST_DELAY = 0       # Delay used when requesting HTML, may be good to have to prevent being banned from the site

INITIAL_SCORE = 100     # Starting value for score before deductions are taken.
GOOD_SCORE = 98         # Score required to short-circuit matching and stop searching.
IGNORE_SCORE = 45       # Any score lower than this will be ignored.

THREAD_MAX = 20

def Start():
    #HTTP.ClearCache()
    HTTP.CacheTime = CACHE_1WEEK
    HTTP.Headers['User-agent'] = 'Mozilla/4.0 (compatible; MSIE 8.0; Windows NT 6.2; Trident/4.0; SLCC2; .NET CLR 2.0.50727; .NET CLR 3.5.30729; .NET CLR 3.0.30729; Media Center PC 6.0)'
    HTTP.Headers['Accept-Encoding'] = 'gzip'

class VRPHub(Agent.Movies):
    name = 'VRPHub'
    languages = [Locale.Language.NoLanguage]
    primary_provider = True
    accepts_from = ['com.plexapp.agents.localmedia']

    prev_search_provider = 0

    def Log(self, message, *args):
        if Prefs['debug']:
            Log(message, *args)

    def findDateInPage(self, html):
        date = html.xpath('//time')[0].text_content();
        self.Log('***** Date "%s"', date);
        #result = re.search(r'(\d+-\d+-\d+)', title)
        self.Log('***** Date "%s"', Datetime.ParseDate(date));
        return Datetime.ParseDate(date)

    def getStringContentFromXPath(self, source, query):
        return source.xpath('string(' + query + ')')

    def getAnchorUrlFromXPath(self, source, query):
        anchor = source.xpath(query)

        if len(anchor) == 0:
            return None

        return anchor[0].get('href')

    def getImageUrlFromXPath(self, source, query):
        img = source.xpath(query)

        if len(img) == 0:
            return None

        return img[0].get('src')

    def findDateInTitle(self, title):
        result = re.search(r'(\d+-\d+-\d+)', title)
        if result is not None:
            return Datetime.ParseDate(result.group(0)).date()
        return None

    def doSearch(self, url):
        html = HTML.ElementFromURL(url, sleep=REQUEST_DELAY)

        found = []
        for r in html.xpath('//div[a/img[@class="yborder"]]'):
            date = self.getDateFromString(self.getStringContentFromXPath(r, 'text()[1]'))
            title = self.getStringContentFromXPath(r, 'a[2]')
            murl = self.getAnchorUrlFromXPath(r, 'a[2]')
            thumb = self.getImageUrlFromXPath(r, 'a/img')

            found.append({'url': murl, 'title': title, 'date': date, 'thumb': thumb})

        return found

    def search(self, results, media, lang, manual=False):
        if media.name:

            self.Log('Media.name')
            # Make url
            url = D18_MOVIE_INFO % media.name
            # Fetch HTML
            html = HTML.ElementFromURL(url, sleep=REQUEST_DELAY)
            # Set the result
            results.Append(MetadataSearchResult(id = media.name, name  = self.getStringContentFromXPath(html, '//h1'), score = '100', lang = lang))

    def update(self, metadata, media, lang, force=False):
        self.Log('***** UPDATING "%s" ID: %s - VRPHub v.%s *****', media.title, metadata.id, VERSION_NO)

        # Make url
        url = D18_MOVIE_INFO % metadata.id

        try:
            # Fetch HTML
            html = HTML.ElementFromURL(url, sleep=REQUEST_DELAY)

            # Set tagline to URL
            metadata.tagline = url

            # Get the date
#            date = self.findDateInTitle(media.title)
            date = self.findDateInPage(html)

            # Set the date and year if found.
#            if date is not None:
#                metadata.originally_available_at = date
            metadata.originally_available_at = date
            metadata.year = date.year

            # Get the title
            metadata.title = self.getStringContentFromXPath(html, '//h1')

            # Set the summary
            paragraph = html.xpath('//h5')
            if len(paragraph) > 0:
                summary = paragraph[0].text_content().strip('\n').strip()
#                summary = re.sub(r'Description:', '', summary.strip())
                metadata.summary = summary

            # def getStringContentFromXPath(self, source, query):
            #     return source.xpath('string(' + query + ')')

            # Set the studio, and director
            #/html/body/div[5]/div[1]/div/div[2]/p/span/span/span/a
            studio_and_director = html.xpath('//a[@typeof="v:Breadcrumb"]/text()')
            if len(studio_and_director) > 0:
                try:
                    metadata.studio = self.getStringContentFromXPath(studio_and_director[0], 'a[1]')
                except:
                    Log.Error('Error obtaining data for item with id %s (%s) [%s] ', metadata.id, url, e.message)

            # Add the genres
            metadata.genres.clear()
            genres = html.xpath('//div[@class="post-tags"]//a')
            for genre in genres:
                genre = genre.text.strip()
                if len(genre) > 0 and re.match(r'Tags:', genre) is None:
                    metadata.genres.add(genre)

            # Add the performers
            metadata.roles.clear()
            performers = html.xpath('//h6/strong[contains(., "Featuring")]/span/text()')
            Log.Error('performers = %s', performers);
            if performers[0].find(",") != -1:
                performers = performers[0].split(',')
            Log.Error('performers = %s', performers);
            for performer in performers:
                Log.Error('performer = %s', performer);
                role = metadata.roles.new()
                role.name = performer.strip()

                # Get the url for performer photo
#               role.photo = re.sub(r'/stars/60/', '/stars/pic/', performer.get('src'))

                # Get posters and fan art.
                self.getImages(url, html, metadata, force)
        except Exception, e:
            Log.Error('Error obtaining data for item with id %s (%s) [%s] ', metadata.id, url, e.message)

        self.writeInfo('New data', url, metadata)

    def hasProxy(self):
        return Prefs['imageproxyurl'] is not None

    def makeProxyUrl(self, url, referer):
        return Prefs['imageproxyurl'] + ('?url=%s&referer=%s' % (url, referer))

    def worker(self, queue, stoprequest):
        while not stoprequest.isSet():
            try:
                func, args, kargs = queue.get(True, 0.05)
                try: func(*args, **kargs)
                except Exception, e: self.Log(e)
                queue.task_done()
            except Queue.Empty:
                continue

    def addTask(self, queue, func, *args, **kargs):
        queue.put((func, args, kargs))

    def getImages(self, url, mainHtml, metadata, force):
        queue = Queue.Queue(THREAD_MAX)
        stoprequest = Thread.Event()
        for _ in range(THREAD_MAX): Thread.Create(self.worker, self, queue, stoprequest)

        results = []

        self.addTask(queue, self.getPosters, url, mainHtml, metadata, results, force, queue)

        scene_image_max = 20
#        try:
#            scene_image_max = int(Prefs['sceneimg'])
#        except:
#            Log.Error('Unable to parse the Scene image count setting as an integer.')
#
#        if scene_image_max >= 0:
##/html/body/div[5]/div[1]/div/div[2]/div[1]/article/div/div/div/div[1]/div/div/div/div/div[1]/a/img
#            for i, scene in enumerate(mainHtml.xpath('//div[p//b[contains(text(),"Scene ")]]')):
#                sceneName = self.getStringContentFromXPath(scene, 'p//b[contains(text(),"Scene ")]')
#                sceneUrl = self.getAnchorUrlFromXPath(scene, './/a[contains(@href, "go.data18.com") and img]')
#                if sceneUrl is not None:
#                    #download all the images directly when they are referenced offsite
#                    self.Log('Found scene (%s) - Getting art directly', sceneName)
#                    self.addTask(queue, self.getSceneImagesFromAlternate, i, scene, url, metadata, scene_image_max, results, force, queue)
#                    continue
#
#                sceneUrl = self.getAnchorUrlFromXPath(scene, './/a[not(contains(@href, "download") ) and img]')
#                if sceneUrl is None:
#                    continue
#
#                self.Log('Found scene (%s) - Trying to get fan art from [%s]', sceneName, sceneUrl)
#
#                self.addTask(queue, self.getSceneImages, i, sceneUrl, metadata, scene_image_max, results, force, queue)
#
        scenearts = mainHtml.xpath('//div[@class="et_pb_gallery_image landscape"]//a')
        #Log.Error('scenearts %s', scenearts);
        i = 0
        for sceneart in scenearts:
            Log.Error('sceneart %s', sceneart);
            sceneUrl = sceneart.get('href')
            Log.Error('sceneurl %s', sceneUrl);
            i = i + 1
            self.addTask(queue, self.downloadImage, sceneUrl, sceneUrl, url, False, i, 0, results)
#            self.addTask(queue, self.downloadImage, imageUrl, imageUrl, url, False, i, -1, results)
#            self.addTask(queue, self.getSceneImages, i, sceneUrl, metadata, scene_image_max, results, force, queue)

        Log.Error('finished getting poster');
        queue.join()
        stoprequest.set()
        Log.Error('double finished getting poster');
        #Log.Error('double finished getting poster results %s', results);

        from operator import itemgetter
        for i, r in enumerate(sorted(results, key=itemgetter('scene', 'index'))):
#            self.Log('r  %s & i %s', r, i)
            if r['isPreview']:
                proxy = Proxy.Preview(r['image'], sort_order=i+1)
            else:
                proxy = Proxy.Media(r['image'], sort_order=i+1)

            if r['scene'] > -1:
                metadata.posters[r['url']] = proxy
            else:
#                self.Log('added poster %s (%s)', r['url'], i)
                metadata.art[r['url']] = proxy

    def getPosters(self, url, mainHtml, metadata, results, force, queue):
#        get_poster_alt = Prefs['posteralt']
        i = 0
#
#        #get full size posters
#        #for poster in mainHtml.xpath('//a[@data-lightbox="covers"]/@href'):
#        for poster in mainHtml.xpath('//a[@rel="covers"]/@href'):
#            #self.Log('found %s', poster)
#            if 'frontback' in poster:
#                continue
#            if poster in metadata.posters.keys() and not force:
#                continue
#            self.addTask(queue, self.downloadImage, poster, poster, url, False, i, -1, results)
#            i += 1
#        #Check for combined poster image and use alternates if available
#        if get_poster_alt and i == 0:
#            self.getPosterFromAlternate(url, mainHtml, metadata, results, force, queue)
#            i = len(metadata.posters)
#
#        #Always get the lower-res poster from the main page that tends to be just the front cover.  This is close to 100% reliable
        try:
            imageUrl = self.getImageUrlFromXPath(mainHtml, '//div/a/img[@alt=""]')
            Log.Error('poster image url = %s', imageUrl);
            self.addTask(queue, self.downloadImage, imageUrl, imageUrl, url, False, i, -1, results)
            Log.Error('added task poster image url = %s', imageUrl);
        except:
            Log.Error('Error getting poster %s', e.message)


    def getSceneImages(self, sceneIndex, sceneUrl, metadata, sceneImgMax, result, force, queue):
        sceneHtml = HTML.ElementFromURL(sceneUrl, sleep=REQUEST_DELAY)
        sceneTitle = self.getStringContentFromXPath(sceneHtml, '//h1[@class="h1big"]')

        imgCount = 0
        images = sceneHtml.xpath('//a[img[contains(@alt,"image")]]/img')
        if images is not None and len(images) > 0:
            firstImage = images[0].get('src')
            thumbPatternSearch = re.search(r'(th\w*)/', firstImage)
            thumbPattern = None
            if thumbPatternSearch is not None:
                thumbPattern = thumbPatternSearch.group(1)
            #get viewer page
            firstViewerPageUrl = images[0].xpath('..')[0].get('href')
            html = HTML.ElementFromURL(firstViewerPageUrl, sleep=REQUEST_DELAY)

            imageCount = None
            imageCountSearch = re.search(r'Image \d+ of (\d+)', html.text_content())
            if imageCountSearch is not None:
                imageCount = int(imageCountSearch.group(1))
            else:
                # No thumbs were found on the page, which seems to be the case for some scenes where there are only 4 images
                # so let's just pretend we found thumbs
                imageCount = 4

            # plex silently dies or kills this off if it downloads too much stuff, especially if there are errors. have to manually limit numbers of images for now
            # workaround!!!
            if imageCount > 3:
                imageCount = 3

            # Find the actual first image on the viewer page
            imageUrl = self.getImageUrlFromXPath(html, '//div[@id="post_view"]//img')

            # Go through the thumbnails replacing the id of the previous image in the imageUrl on each iteration.
            for i in range(1,imageCount+1):
                imgId = '%02d' % i
                imageUrl = re.sub(r'\d{1,3}.jpg', imgId + '.jpg', imageUrl)
                thumbUrl = None
                if thumbPattern is not None:
                    thumbUrl = re.sub(r'\d{1,3}.jpg', imgId + '.jpg', firstImage)

                if imgCount > sceneImgMax:
                    #self.Log('Maximum background art downloaded')
                    break
                imgCount += 1

                if self.hasProxy():
                    imgUrl = self.makeProxyUrl(imageUrl, firstViewerPageUrl)
                    thumbUrl = None
                else:
                    imgUrl = imageUrl
                    thumbUrl = None

                if not imgUrl in metadata.art.keys() or force:
                    if thumbUrl is not None:
                        self.addTask(queue, self.downloadImage, thumbUrl, imgUrl, firstViewerPageUrl, True, i, sceneIndex, result)
                    else:
                        self.addTask(queue, self.downloadImage, imgUrl, imgUrl, firstViewerPageUrl, False, i, sceneIndex, result)

        if imgCount == 0:
            # Use the player image from the main page as a backup
            playerImg = self.getImageUrlFromXPath(sceneHtml, '//img[@alt="Play this Video" or contains(@src,"/hor.jpg")]')
            if playerImg is not None and len(playerImg) > 0:
                if self.hasProxy():
                    img = self.makeProxyUrl(playerImg, sceneUrl)
                else:
                    img = playerImg

                if not img in metadata.art.keys() or force:
                    self.addTask(queue, self.downloadImage, img, img, sceneUrl, False, 0, sceneIndex, result)



    #download the images directly from the main page
    def getSceneImagesFromAlternate(self, sceneIndex, sceneHtml, url, metadata, sceneImgMax, result, force, queue):
        self.Log('Attempting to get art from main page')
        i = 0
        for imageUrl in sceneHtml.xpath('.//a[not(contains(@href, "download") ) and img]/img/@src'):
            if sceneImgMax > 0 and i + 1 > sceneImgMax:
                break

            if self.hasProxy():
                imgUrl = self.makeProxyUrl(imageUrl, url)
            else:
                imgUrl = imageUrl

            if not imgUrl in metadata.art.keys() or force:
                #self.Log('Downloading %s', imageUrl)
                self.addTask(queue, self.downloadImage, imgUrl, imgUrl, url, False, i, sceneIndex, result)
                i += 1


    def getPosterFromAlternate(self, url, mainHtml, metadata, results, force, queue):
        provider = ''

        # Prefer AEBN, since the poster seems to be better quality there.
        altUrl = self.getAnchorUrlFromXPath(mainHtml, '//a[b[contains(text(),"AEBN")]]')
        if altUrl is not None:
            provider = 'AEBN'
        else:
            provider = 'VRPHubStore'
            altUrl = self.getAnchorUrlFromXPath(mainHtml, '//a[contains(text(),"Available for")]')


        if altUrl is not None:
            self.Log('Attempting to get poster from alternative location (%s) [%s]', provider, altUrl)

            providerHtml = HTML.ElementFromURL(altUrl, sleep=REQUEST_DELAY)
            frontImgUrl = None
            backImgUrl = None

            if provider is 'AEBN':
                frontImgUrl = self.getAnchorUrlFromXPath(providerHtml, '//div[@id="md-boxCover"]/a[1]')
                if frontImgUrl is not None:
                    backImgUrl = frontImgUrl.replace('_xlf.jpg', '_xlb.jpg')
            else:
                frontImgUrl = self.getImageUrlFromXPath(providerHtml, '//div[@id="gallery"]//img')
                if frontImgUrl is not None:
                    backImgUrl = frontImgUrl.replace('h.jpg', 'bh.jpg')

            if frontImgUrl is not None:
                if not frontImgUrl in metadata.posters.keys() or force:
                    self.addTask(queue, self.downloadImage, frontImgUrl, frontImgUrl, altUrl, False, 1, -1, results)

                if not backImgUrl is None and (not backImgUrl in metadata.posters.keys() or force):
                    self.addTask(queue, self.downloadImage, backImgUrl, backImgUrl, altUrl, False, 2, -1, results)
                return True
        return False

    def downloadImage(self, url, referenceUrl, referer, isPreview, index, sceneIndex, results):
        results.append({'url': referenceUrl, 'image': HTTP.Request(url, cacheTime=0, headers={'Referer': referer}, sleep=REQUEST_DELAY).content, 'isPreview': isPreview, 'index': index, 'scene': sceneIndex})

    ### Writes metadata information to log.
    def writeInfo(self, header, url, metadata):
        self.Log(header)
        self.Log('-----------------------------------------------------------------------')
        self.Log('* ID:              %s', metadata.id)
        self.Log('* URL:             %s', url)
        self.Log('* Title:           %s', metadata.title)
        self.Log('* Release date:    %s', str(metadata.originally_available_at))
        self.Log('* Year:            %s', metadata.year)
        self.Log('* Studio:          %s', metadata.studio)
        self.Log('* Director:        %s', metadata.directors[0] if len(metadata.directors) > 0  else '')
        self.Log('* Tagline:         %s', metadata.tagline)
        self.Log('* Summary:         %s', metadata.summary)

        if len(metadata.collections) > 0:
            self.Log('|\\')
            for i in range(len(metadata.collections)):
                self.Log('| * Collection:    %s', metadata.collections[i])

        if len(metadata.roles) > 0:
            self.Log('|\\')
            for i in range(len(metadata.roles)):
                self.Log('| * Starring:      %s (%s)', metadata.roles[i].name, metadata.roles[i].photo)

        if len(metadata.genres) > 0:
            self.Log('|\\')
            for i in range(len(metadata.genres)):
                self.Log('| * Genre:         %s', metadata.genres[i])

        if len(metadata.posters) > 0:
            self.Log('|\\')
            for poster in metadata.posters.keys():
                self.Log('| * Poster URL:    %s', poster)

        if len(metadata.art) > 0:
            self.Log('|\\')
            for art in metadata.art.keys():
                self.Log('| * Fan art URL:   %s', art)

        self.Log('***********************************************************************')

def safe_unicode(s, encoding='utf-8'):
    if s is None:
        return None
    if isinstance(s, basestring):
        if isinstance(s, types.UnicodeType):
            return s
        else:
            return s.decode(encoding)
    else:
        return str(s).decode(encoding)

#vrphub = VRPHub();
#results = {};
#vrphub.search(vrphub, results, media, lang, manual=False)
