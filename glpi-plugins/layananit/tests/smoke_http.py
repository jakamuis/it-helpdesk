"""Local GLPI fixture only: authenticated pages, anonymous guard and machine-feed rejection."""
import json
import os
import subprocess
import urllib.request
import urllib.error
import uuid

if os.environ.get('ITREQUEST_TEST_LOCAL') != '1':
    raise SystemExit('Local fixture only: set ITREQUEST_TEST_LOCAL=1')
container = os.environ.get('GLPI_TEST_CONTAINER', 'glpi_app')
base = 'http://localhost:8080'
cookie = urllib.request.urlopen(base).headers['Set-Cookie'].split('=', 1)[0]
prefix = "$_SERVER['HTTP_HOST']='localhost:8080'; $_SERVER['SERVER_PORT']='80'; require '/var/www/glpi/vendor/autoload.php'; $k=new Glpi\\Kernel\\Kernel(); $k->boot(); "
prefix += 'session_name(' + json.dumps(cookie) + '); session_save_path(GLPI_SESSION_DIR); '
code = prefix + "Session::start(); $u=new User(); $u->getFromDBbyName('glpi'); $a=new Auth(); $a->auth_succeded=true; $a->user=$u; Session::init($a); echo json_encode([session_name(),session_id()]); session_write_close();"
r = subprocess.run(['docker', 'exec', '-u', 'www-data', container, 'php', '-r', code], check=True, capture_output=True, text=True)
name, sid = json.loads(r.stdout)
fixture_title = 'LOCAL INCIDENT REGRESSION ' + uuid.uuid4().hex
fixture_id = 0
try:
    create = prefix + 'session_id(' + json.dumps(sid) + '); Session::start(); $t=new Ticket(); echo $t->add(["name"=>' + json.dumps(fixture_title) + ',"content"=>"Local UI regression fixture","type"=>1,"entities_id"=>0,"_disablenotif"=>true]);'
    result = subprocess.run(['docker','exec','-u','www-data',container,'php','-r',create], check=True, capture_output=True, text=True)
    fixture_id = int(result.stdout.strip())
    assert fixture_id > 0
    for page in ['dashboard', 'incident', 'request', 'Computer', 'Monitor', 'Printer', 'users', 'more']:
        url = base + '/plugins/layananit/front/index.php?page=' + page
        with urllib.request.urlopen(urllib.request.Request(url, headers={'Cookie': name + '=' + sid})) as response:
            html = response.read().decode()
            assert response.status == 200 and 'lti-sidebar' in html and 'An unexpected error occurred' not in html
        if page == 'incident':
            assert fixture_title in html, 'Incident list must render the actual fixture ticket'
            assert 'Reset dashboard to default' not in html, 'Incident list must not insert the mini dashboard'
            assert 'name="page" value="incident"' in html or "name='page' value='incident'" in html, 'Search must retain Incident navigation'
        print('PASS authenticated Layanan TI', page)
    with urllib.request.urlopen(base + '/plugins/layananit/front/index.php') as response:
        assert 'lti-sidebar' not in response.read().decode()
    try:
        urllib.request.urlopen(base + '/plugins/itrequest/front/wa-feed.php')
        raise AssertionError('Anonymous feed must be forbidden')
    except urllib.error.HTTPError as error:
        assert error.code == 403
    print('PASS anonymous UI and feed guards')
finally:
    if fixture_id:
        cleanup = prefix + 'session_id(' + json.dumps(sid) + '); Session::start(); $t=new Ticket(); $t->delete(["id"=>' + str(fixture_id) + ',"_disablenotif"=>true],true);'
        subprocess.run(['docker','exec','-u','www-data',container,'php','-r',cleanup], check=True, capture_output=True)
    subprocess.run(['docker', 'exec', '-u', 'www-data', container, 'php', '-r', prefix + 'session_id(' + json.dumps(sid) + '); Session::start(); session_destroy();'], check=True, capture_output=True)
