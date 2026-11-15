"""LOCAL ONLY: authenticated HTTP checks, temporary draft/file and session cleaned in finally.
Run from the laptop with ITREQUEST_TEST_LOCAL=1; requires docker and local GLPI.
"""
import os
if os.environ.get('ITREQUEST_TEST_LOCAL') != '1':
    raise SystemExit('Local test only: set ITREQUEST_TEST_LOCAL=1')
import subprocess, json, urllib.request, urllib.parse, urllib.error, re, uuid, base64
prefix="$_SERVER['HTTP_HOST']='localhost:8080'; $_SERVER['SERVER_PORT']='80'; require '/var/www/glpi/vendor/autoload.php'; $k = new Glpi\\Kernel\\Kernel(); $k->boot(); "
cookie=urllib.request.urlopen('http://localhost:8080/').headers['Set-Cookie'].split('=',1)[0]
prefix += 'session_name('+json.dumps(cookie)+'); session_save_path(GLPI_SESSION_DIR); '
code=prefix+"Session::start(); $u=new User(); $u->getFromDBbyName('glpi'); $a=new Auth(); $a->auth_succeded=true; $a->user=$u; Session::init($a); echo json_encode([session_name(), session_id()]); session_write_close();"
r=subprocess.run(['docker','exec','-u','www-data',os.environ.get('GLPI_TEST_CONTAINER', 'glpi_app'),'php','-r',code],capture_output=True,text=True,check=True)
name,sid=json.loads(r.stdout)
base='http://localhost:8080/plugins/itrequest/'
fixture_id=0
try:
    for path in ['front/index.php','front/index.php?tab=new','front/index.php?tab=settings']:
        req=urllib.request.Request(base+path,headers={'Cookie':name+'='+sid})
        with urllib.request.urlopen(req) as res:
            html=res.read().decode()
            assert res.status==200 and '<h1>Request IT</h1>' in html,(path,html[-1200:])
            if 'tab=new' in path:
                assert 'request-type' in html and 'enctype="multipart/form-data"' in html
            if 'tab=settings' in path:
                assert 'Simpan pemetaan atasan' in html
            print('PASS HTTP authenticated GET',path)
    req=urllib.request.Request(base+'front/action.php',data=urllib.parse.urlencode({'action':'create','type':'email','email_service':'new'}).encode(),headers={'Cookie':name+'='+sid})
    try:
        with urllib.request.urlopen(req) as res:
            body=res.read().decode()
            assert res.status in (400,403) or 'not allowed' in body.lower() or 'action you have requested' in body.lower(), (res.status,body[-500:])
    except urllib.error.HTTPError as e:
        assert e.code in (400,403),e.code
    print('PASS HTTP POST without CSRF blocked')
    def get(path):
        with urllib.request.urlopen(urllib.request.Request(base+path,headers={'Cookie':name+'='+sid})) as response:
            return response.read().decode()
    def token(html):
        return re.search(r'name="_glpi_csrf_token" value="([^"]+)"',html).group(1)
    new=get('front/index.php?tab=new')
    fields={'action':'create','type':'email','email_service':'new','title':'LOCAL HTTP TEST '+str(uuid.uuid4()),'_glpi_csrf_token':token(new)}
    request=urllib.request.Request(base+'front/action.php',data=urllib.parse.urlencode(fields).encode(),headers={'Cookie':name+'='+sid})
    with urllib.request.urlopen(request) as response:
        html=response.read().decode()
        fixture_id=int(urllib.parse.parse_qs(urllib.parse.urlparse(response.url).query)['id'][0])
        assert fields['title'] in html
    print('PASS HTTP POST draft with CSRF')
    version=re.search(r'name="version" value="([^"]+)"',html).group(1)
    boundary='----itrequest'+uuid.uuid4().hex
    chunks=[]
    for key,value in {'action':'upload','id':str(fixture_id),'version':version,'_glpi_csrf_token':token(html)}.items():
        chunks.append(('--'+boundary+'\r\nContent-Disposition: form-data; name="'+key+'"\r\n\r\n'+value+'\r\n').encode())
    png=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6sAAAAABJRU5ErkJggg==')
    chunks.append(('--'+boundary+'\r\nContent-Disposition: form-data; name="attachment"; filename="bukti.png"\r\nContent-Type: image/png\r\n\r\n').encode()+png+b'\r\n')
    chunks.append(('--'+boundary+'--\r\n').encode())
    request=urllib.request.Request(base+'front/action.php',data=b''.join(chunks),headers={'Cookie':name+'='+sid,'Content-Type':'multipart/form-data; boundary='+boundary})
    with urllib.request.urlopen(request) as response:
        html=response.read().decode()
        fileid=int(re.search(r'download.php\?id=(\d+)',html).group(1))
    with urllib.request.urlopen(urllib.request.Request(base+'front/download.php?id='+str(fileid),headers={'Cookie':name+'='+sid})) as response:
        assert response.read()==png
        assert 'attachment' in response.headers['Content-Disposition'] and 'bukti.png' in response.headers['Content-Disposition']
    print('PASS HTTP authenticated upload/download, original filename and binary integrity')

finally:
    if fixture_id:
        cleanup=prefix+"require '/var/www/glpi/plugins/itrequest/inc/attachment.class.php'; $id="+str(fixture_id)+"; foreach (PluginItrequestService::rows('attachments',['requests_id'=>$id]) as $a) { $p=PluginItrequestAttachment::directory().'/'.$a['storage_key']; if (is_file($p)) unlink($p); } foreach (['attachments','events'] as $t) $DB->delete(PluginItrequestService::PREFIX.$t,['requests_id'=>$id]); $DB->delete(PluginItrequestService::PREFIX.'requests',['id'=>$id]);"
        subprocess.run(['docker','exec','-u','www-data',os.environ.get('GLPI_TEST_CONTAINER', 'glpi_app'),'php','-r',cleanup],capture_output=True,check=True)
    destroy=prefix+'session_id('+json.dumps(sid)+'); Session::start(); session_destroy();'
    subprocess.run(['docker','exec','-u','www-data',os.environ.get('GLPI_TEST_CONTAINER', 'glpi_app'),'php','-r',destroy],capture_output=True,check=True)
