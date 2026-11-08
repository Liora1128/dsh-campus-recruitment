"""Bounded public retrieval, robots compliance, no login or challenge bypass."""
import ipaddress
import json
import re
import socket
import time
import zlib
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urlsplit, urljoin, urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler, urlopen
from urllib.robotparser import RobotFileParser

UA='CampusRecruitmentResearch/1.0'
MAX_BYTES=8*1024*1024
MAX_DECODED_BYTES=12*1024*1024
FETCH_VERSION='public-browser-v2'
DNS_CACHE={}

def access_challenge(text):
    return bool(re.search(r'人机验证|安全验证|请完成.{0,8}验证|为了您的账户安全|访问过于频繁|just a moment|access denied|登录后.{0,8}(?:查看|浏览)(?!联系|电话|手机|邮箱)|扫码登录后|请先登录后.{0,4}查看',text[:6000],re.I))

def structured_text(blocks):
    """Only explicitly typed JobPosting metadata; never infer a publish date."""
    jobs=[]
    def walk(value):
        if isinstance(value,list):
            for item in value:walk(item)
        elif isinstance(value,dict):
            kind=value.get('@type')
            if kind=='JobPosting' or isinstance(kind,list) and 'JobPosting' in kind:
                # Exclude unrelated analytics and arbitrary executable script state.
                jobs.append({k:value[k] for k in ('title','description','hiringOrganization','jobLocation','datePosted','validThrough','employmentType','identifier','educationRequirements','experienceRequirements') if k in value})
            if '@graph' in value:walk(value['@graph'])
    walk(blocks)
    result=[]
    for job in jobs[:10]:
        result.append('页面公开结构化招聘原文（JSON-LD JobPosting）：\n'+json.dumps(job,ensure_ascii=False))
        description=job.get('description')
        if isinstance(description,str):
            parser=PageParser();parser.feed(description);result.append('\n'.join(parser.parts))
    return '\n'.join(result)

def public_url(url):
    p=urlsplit(url)
    if p.scheme not in ('http','https') or not p.hostname or p.username or p.password or p.port not in (None,80,443): raise ValueError('不允许的公开链接')
    if p.hostname.lower()=='localhost' or p.hostname.lower().endswith(('.localhost','.local','.internal','.lan')):raise ValueError('拒绝本地域名')
    if p.hostname in DNS_CACHE:return url
    addresses=[ipaddress.ip_address(a[4][0]) for a in socket.getaddrinfo(p.hostname,p.port or (443 if p.scheme=='https' else 80),type=socket.SOCK_STREAM)]
    if not addresses:raise ValueError('域名无有效地址')
    if any(not a.is_global for a in addresses):
        # A TUN proxy can synthesize benchmark-range DNS answers. Independently
        # verify the public hostname via TLS DoH; never allow literal/private IPs.
        try:ipaddress.ip_address(p.hostname);literal=True
        except ValueError:literal=False
        if literal or not all(a in ipaddress.ip_network('198.18.0.0/15') for a in addresses):raise ValueError('拒绝访问本机或私网地址')
        request=Request('https://dns.google/resolve?'+urlencode({'name':p.hostname,'type':'A'}),headers={'Accept':'application/dns-json','User-Agent':UA})
        try:
            with urlopen(request,timeout=8) as response:data=json.loads(response.read(100000))
            public=[ipaddress.ip_address(a['data']) for a in data.get('Answer',[]) if a['type'] in (1,28)]
            if data.get('Status')!=0 or not public or any(not a.is_global for a in public):raise ValueError()
        except Exception:raise ValueError('Fake-IP 域名未通过独立公共DNS核验') from None
    DNS_CACHE[p.hostname]=True
    return url

class SafeRedirect(HTTPRedirectHandler):
    def __init__(self,authorize=None):super().__init__();self.authorize=authorize
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        public_url(newurl)
        if self.authorize:self.authorize(newurl)
        return super().redirect_request(req,fp,code,msg,headers,newurl)

class PageParser(HTMLParser):
    def __init__(self):super().__init__();self.parts=[];self.skip=0;self.jsonld=[];self.in_json=False;self.raw='';self.links=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag in ('script','style','noscript'):
            self.skip+=1
            if tag=='script' and 'ld+json' in a.get('type',''):self.in_json=True;self.raw=''
        if tag=='a' and a.get('href'):self.links.append(a['href'])
    def handle_endtag(self,tag):
        if tag in ('script','style','noscript'):
            if self.in_json and tag=='script':
                try:self.jsonld.append(json.loads(self.raw))
                except ValueError:pass
                self.in_json=False
            self.skip=max(0,self.skip-1)
    def handle_data(self,data):
        if self.in_json:self.raw+=data
        elif not self.skip and data.strip():self.parts.append(data.strip())

class Fetcher:
    def __init__(self,root=None,renderer=None,max_dynamic=10):
        self.robots={};self.opener=build_opener(SafeRedirect());self.last={}
        self.root=Path(root) if root else Path(__file__).resolve().parents[1]
        self.renderer=renderer;self.max_dynamic=max_dynamic;self.dynamic_count=0;self.last_robots_error=''
    def raw(self,url,*,page=False):
        public_url(url)
        req=Request(url,headers={'User-Agent':UA,'Accept':'text/html,application/json,text/plain;q=0.8','Accept-Encoding':'gzip'})
        opener=build_opener(SafeRedirect(self.check_robots)) if page else self.opener
        with opener.open(req,timeout=15) as response:
            content_type=response.headers.get_content_type()
            if content_type not in ('text/html','application/json','text/plain','application/ld+json'):raise ValueError('不支持的页面类型')
            limit=MAX_BYTES if page else 512*1024
            raw=response.read(limit+1)
            if len(raw)>limit:raise ValueError('PAGE_SIZE_LIMIT：页面超过8MiB有界读取上限' if page else 'ROBOTS_SIZE_LIMIT')
            if response.headers.get('Content-Encoding','').lower()=='gzip':
                decoder=zlib.decompressobj(16+zlib.MAX_WBITS);raw=decoder.decompress(raw,MAX_DECODED_BYTES+1)
                if len(raw)>MAX_DECODED_BYTES or decoder.unconsumed_tail:raise ValueError('DECODED_SIZE_LIMIT：解压后页面超过12MiB上限')
            charset=response.headers.get_content_charset() or 'utf-8'
            # Many public campus portals use GBK but omit the HTTP charset.
            header=raw[:1500].decode('ascii','ignore')
            match=re.search(r'charset=["\s]*([\w-]+)',header,re.I)
            if match:charset=match.group(1)
            try:text=raw.decode(charset)
            except (UnicodeError,LookupError):text=raw.decode('gb18030',errors='replace')
            return response.url,text
    def check_robots(self,url):
        public_url(url);p=urlsplit(url);origin=p.scheme+'://'+p.netloc
        if origin not in self.robots:
            robot=RobotFileParser();robot.set_url(origin+'/robots.txt')
            try:
                _,text=self.raw(robot.url);robot.parse(text.splitlines())
            except Exception as e:
                # Only a real missing robots file permits fallback; network/auth errors do not.
                if getattr(e,'code',None) in (404,410):robot.parse([])
                else:raise ValueError('ROBOTS_UNAVAILABLE：无法核实robots.txt（'+str(getattr(e,'code',type(e).__name__))+')，暂不采集') from None
            self.robots[origin]=robot
        robot=self.robots[origin]
        if not robot.can_fetch(UA,url):raise ValueError('ROBOTS_DISALLOW：robots.txt不允许采集')
        delay=max(1,robot.crawl_delay(UA) or robot.crawl_delay('*') or 1)
        rate=robot.request_rate(UA) or robot.request_rate('*')
        if rate and rate.requests:delay=max(delay,rate.seconds/rate.requests)
        if delay>10:raise ValueError('站点要求较长访问间隔，本次跳过以遵守规则')
        wait=delay-(time.monotonic()-self.last.get(origin,0))
        if wait>0:time.sleep(wait)
        self.last[origin]=time.monotonic()
    def browser_authorize(self,url,resource_type):
        public_url(url)
        # Read the public document and API only where the site's robots permit it.
        # Static script/style loads are needed to render the same public page.
        if resource_type in ('Document','XHR','Fetch'):self.check_robots(url)
    def fetch(self,url):
        self.check_robots(url)
        final,html=self.raw(url,page=True)
        parser=PageParser();parser.feed(html)
        text='\n'.join(parser.parts)
        if access_challenge(text):raise ValueError('CAPTCHA_OR_LOGIN_REQUIRED：页面要求安全验证或登录，已跳过')
        metadata=structured_text(parser.jsonld)
        if metadata:text+='\n'+metadata
        page={'url':final,'text':text[:40000],'jsonld':parser.jsonld,'links':[urljoin(final,x) for x in parser.links][:160],'method':'http','fetch_version':FETCH_VERSION,'html_bytes':len(html.encode('utf-8')),'http_status':200}
        detail_heading=re.search(r'职位详情|职位介绍',text)
        fragment=re.split(r'工作地址|公司信息|其他职位',text[detail_heading.end():],maxsplit=1)[0] if detail_heading else ''
        missing_detail=bool(detail_heading and len(fragment.strip())<100)
        if len(text)>=120 and not missing_detail:return page
        if self.dynamic_count>=self.max_dynamic:raise ValueError('DYNAMIC_BUDGET：本次动态页面预算已用完')
        self.dynamic_count+=1
        renderer=self.renderer
        if renderer is None:
            from .dynamic import render
            renderer=render
        rendered=renderer(final,self.browser_authorize,self.root)
        self.check_robots(rendered['url'])
        if access_challenge(rendered.get('text','')):raise ValueError('CAPTCHA_OR_LOGIN_REQUIRED：浏览器遇到验证或登录要求，已停止')
        rendered_metadata=structured_text(rendered.get('jsonld',[]))
        if rendered_metadata:rendered['text']+='\n'+rendered_metadata
        if len(rendered.get('text',''))<120:raise ValueError('DYNAMIC_CONTENT_UNAVAILABLE：浏览器未获得公开职位正文')
        return {**rendered,'text':rendered['text'][:40000],'fetch_version':FETCH_VERSION}

def queries(day,explore=False,year=2027,keywords=None):
    from datetime import date,timedelta
    start=(date.fromisoformat(day)-timedelta(days=2)).isoformat()
    directions=keywords or ['电气控制 自动化 研发','PLC 工业控制 运动控制','C++ Qt SCADA 上位机','嵌入式软件 Linux STM32','工业物联网 智能制造 研发']
    result=[f'{year} 校园招聘 {k} after:{start}' for k in directions]
    if explore:result+=[f'{year} 校招 控制算法 研发 招聘 官网',f'{year} 硕士 招聘 工业软件 企业 研发']
    return result
