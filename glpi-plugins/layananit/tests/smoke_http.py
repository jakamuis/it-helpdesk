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
    for page in ['dashboard', 'incident', 'request', 'Computer', 'Monitor', 'Printer', 'users', 'report', 'more']:
        url = base + '/plugins/layananit/front/index.php?page=' + page
        with urllib.request.urlopen(urllib.request.Request(url, headers={'Cookie': name + '=' + sid})) as response:
            html = response.read().decode()
            assert response.status == 200 and 'lti-sidebar' in html and 'An unexpected error occurred' not in html
        if page == 'incident':
            assert fixture_title in html, 'Incident list must render the actual fixture ticket'
            assert 'Reset dashboard to default' not in html, 'Incident list must not insert the mini dashboard'
            assert 'name="page" value="incident"' in html or "name='page' value='incident'" in html, 'Search must retain Incident navigation'
        print('PASS authenticated Layanan TI', page)
    def native_page(path):
        return urllib.request.urlopen(urllib.request.Request(base + path, headers={'Cookie': name + '=' + sid}))
    with native_page('/front/ticket.form.php?id=' + str(fixture_id)) as response:
        html = response.read().decode()
        assert 'public/workspace.js' in html
        assert 'public/native-shell.css' in html and 'public/app.css' in html
        assert html.index('public/native-shell.css') < html.index('<body')
    with native_page('/plugins/layananit/front/shell.php?page=incident') as response:
        shell = json.loads(response.read())
        assert 'lti-sidebar' in shell['sidebar'] and 'samator-logo.png' in shell['sidebar']
    with native_page('/front/central.php') as response:
        assert '/plugins/layananit/front/index.php' in response.url
        assert 'lti-sidebar' in response.read().decode()
    with native_page('/front/central.php?legacy=1') as response:
        assert 'public/workspace.js' not in response.read().decode()
    with native_page('/plugins/layananit/front/index.php') as response:
        assert 'lti-sidebar' in response.read().decode()
    print('PASS native ticket workspace, authenticated shell and original GLPI exit')
    def report(query):
        req = urllib.request.Request(base + '/plugins/layananit/front/index.php?page=report&' + query, headers={'Cookie': name + '=' + sid})
        return urllib.request.urlopen(req)
    import csv, io
    with report('from=2026-01-01&until=2026-12-31&csv=1') as response:
        assert 'text/csv' in response.headers['Content-Type']
        records = list(csv.reader(io.StringIO(response.read().decode('utf-8-sig'))))
        assert any(row[0] == str(fixture_id) for row in records[1:])
        assert len(records[0]) == 10
    with report('from=2026-01-01&until=2026-12-31&technician=2147483647&csv=1') as response:
        assert len(list(csv.reader(io.StringIO(response.read().decode('utf-8-sig'))))) == 1
    with report('from=2026-02-30&until=2026-12-31') as response:
        assert 'Tanggal tidak valid.' in response.read().decode()
    with report('from=2026-12-31&until=2026-01-01') as response:
        assert 'Tanggal awal harus' in response.read().decode()
    print('PASS reporting CSV, technician filter, invalid dates and reversed range')
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
