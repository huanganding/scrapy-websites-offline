import scrapy
from urllib.parse import urlparse,urljoin
import os
from lxml import etree
import chardet
from html.parser import HTMLParser

class SkipDownloadedMiddleware:  
    def process_request(self, request, spider):
        url = request.url
        if not (spider.url2path(url).endswith('.html') or spider.url2path(url).endswith('.htm')) and os.path.isfile(spider.url2path(url)): 
            spider.logger.info('资源已存在，不发出请求。')
            raise scrapy.exceptions.IgnoreRequest
        elif os.path.isfile(spider.url2path(url)): 
            spider.logger.info('从本地读取网页。')
            request.meta['localfile'] =  None 
            with open(spider.url2path(url),'rb') as f:
                body = f.read()
                encoding = chardet.detect(body)['encoding']
                body = spider.href_unlocalize(url,body.decode(encoding))
                return scrapy.http.HtmlResponse(request.url,body=body,request=request,encoding=encoding)        
        else:
            pass

class MainSpider(scrapy.Spider):
    name = 'main'     
    finish_info = {}     
    custom_settings = { 'DOWNLOADER_MIDDLEWARES' : {'scrapy_websites_offline.spiders.main.SkipDownloadedMiddleware': 543,},
                        'DOWNLOAD_DELAY' : 0.05,
                        'CONCURRENT_REQUESTS' : 1,
                        'CONCURRENT_REQUESTS_PER_DOMAIN' : 1,
                        'CONCURRENT_REQUESTS_PER_IP' : 1,
                        'LOG_STDOUT' : True,
                        'ROBOTSTXT_OBEY' : False,
                        'USER_AGENT' : 'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.71 Safari/537.36',
                        'DEPTH_PRIORITY' : 1,
                        'SCHEDULER_DISK_QUEUE' : 'scrapy.squeues.PickleFifoDiskQueue',
                        'SCHEDULER_MEMORY_QUEUE' : 'scrapy.squeues.FifoMemoryQueue',
                        # 'LOG_FILE' : 'log.txt',
                        }
    start_urls = ['http://www.sklec.ecnu.edu.cn/']
    root_dir = r'..\Websites' # ./ means dir where you run command 'scrapy'
    localize_xpaths = []
    localize_xpaths.append('//*[@href or @src]') 
    href_xpaths = []
    href_xpaths.append('//*[@href]/@href')   
    href_xpaths.append('//*[@src]/@src')            

    def start_requests(self):
        for url in self.start_urls: 
            if url not in self.finish_info.keys():
                self.finish_info[url] = {'listed': set(), 'finished': set()}
            yield scrapy.Request(url, cb_kwargs={'from_url': url})
    
    def url2path(self,url):  
        netloc = urlparse(url).netloc 
        net_path = urlparse(url).path 
        path = os.path.join(self.root_dir,netloc,*(net_path.split('/'))) 
        end_of_path = os.path.split(path)[-1]
        if '.' not in end_of_path and end_of_path != netloc: # for url like http://www.xxx.com/list/
            path = os.path.join(path,'index.html')           # append 'index.html'
        return path 
     
    def href_localize(self,this_url,text):  
        dom = etree.HTML(text)   
        links = []
        for xpath in self.localize_xpaths:
            links += dom.xpath(xpath)
        root_dir = os.path.join(self.root_dir,urlparse(this_url).netloc)
        path = self.url2path(this_url)
        for link in links:
            keys = ['href','src']
            for key in keys:
                if key in link.keys():
                    url = link.attrib[key] ;url0=url 
                    if url.endswith('/'):
                        url += 'index.html'
                    if url.startswith('/'):                    
                        url = os.path.join(os.path.relpath(root_dir,self.url2path(this_url)),url[1:])[3:] # use [1:] to delete / prefix            
                    elif url.startswith('http'): 
                        url = os.path.relpath(self.url2path(url),self.url2path(this_url))[3:]  # one ../ has to be removed, don't know why                  
                    link.attrib[key] = url  
                    break   
        body = etree.tostring(dom) 
        return body
        
    # def href_localize(self,this_url,text):       
        # re.findall('''(?:href|src)\s*?=\s*?["'].*?["']''','''href='' src = ""''')
        
    def href_unlocalize(self,this_url,text):  
        dom = etree.HTML(text) 
        path = self.url2path(this_url)
        root_dir = os.path.join(self.root_dir,urlparse(this_url).netloc)
        links = []
        for xpath in self.localize_xpaths:
            links += dom.xpath(xpath)
        for link in links:
            keys = ['href','src']
            for key in keys:
                if key in link.keys():
                    url = link.attrib[key] 
                    url_ =  url
                    if url.startswith('..'): # localized url
                        realpath = os.path.normpath(os.path.join(path,'..\\'+url))
                        commonprefix = os.path.commonprefix([realpath,root_dir])
                        if os.path.normpath(commonprefix) == os.path.normpath(root_dir): 
                            url = urljoin(this_url,url.replace('\\','/'))
                        else:  
                            url = 'https://'+os.path.relpath(realpath,self.root_dir).replace('\\','/')
                        link.attrib[key] = url
                    break   
        body = etree.tostring(dom) 
        return body   

    def save(self,response):
        if not 'localfile' in response.request.meta.keys(): 
            path = self.url2path(response.url)
            if not os.path.isdir(os.path.dirname(path)):  
                os.makedirs(os.path.dirname(path),exist_ok=True)  
            body = response.body
            if isinstance(response,scrapy.http.HtmlResponse): 
                body = self.href_localize(response.url,response.text)
            with open(path,'wb') as f: 
                f.write(body)
            self.logger.info('已保存：'+path)

    def parse(self, response, from_url): 
        self.save(response)
        self.finish_info[from_url]['finished'].add(response.url)
        if self.finish_info[from_url]['finished'] == self.finish_info[from_url]['listed']:
            self.logger.info('该页面所有链接下载完成：' + from_url)  
        if isinstance(response,scrapy.http.HtmlResponse): 
            href_list = []
            for xpath in self.href_xpaths:
                href_list += response.xpath(xpath).getall() 
            for url in href_list: 
                url = urljoin(response.url, url)  
                if url not in self.finish_info.keys():
                    self.finish_info[url] = {'listed':set(),'finished':set()} 
                yield scrapy.Request(url, cb_kwargs={'from_url' : url})


