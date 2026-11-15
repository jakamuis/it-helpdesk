<?php
if (PHP_SAPI !== 'cli' || getenv('ITREQUEST_TEST_LOCAL') !== '1') { exit(2); }
require dirname(__DIR__, 3) . '/vendor/autoload.php';
$kernel = new Glpi\Kernel\Kernel(); $kernel->boot();
require_once dirname(__DIR__) . '/inc/service.class.php';
$DB->beginTransaction();
try {
    $s = PluginItrequestService::class;
    $user = new User(); $user->getFromDBbyName('glpi');
    $uid = (int) $user->getID(); $_SESSION['glpiID'] = $uid;
    $id = $s::insert('requests', ['entities_id'=>0,'users_id'=>$uid,'status'=>'done','payload'=>'{"secret":"private"}','created_at'=>date('Y-m-d H:i:s'),'updated_at'=>date('Y-m-d H:i:s')]);
    $DB->delete($s::PREFIX . 'contacts', ['entities_id'=>0,'users_id'=>$uid]);
    $s::insert('contacts', ['entities_id'=>0,'users_id'=>$uid,'chat_id'=>'628123456789@c.us']);
    $s::event($id, 'start', ['note'=>'OLD EVENT BEFORE CONTACT VERIFICATION']);
    $last = $s::rows('events', [], ['ORDER'=>'id DESC','LIMIT'=>1])[0];
    $s::update('contacts', ['after_event_id'=>(int) $last['id']], ['entities_id'=>0,'users_id'=>$uid]);
    $s::event($id, 'finish', ['note'=>'SECRET NOT FOR WHATSAPP']);
    $foreign = $s::insert('requests', ['entities_id'=>999999,'users_id'=>$uid,'status'=>'done','payload'=>'{}','created_at'=>date('Y-m-d H:i:s'),'updated_at'=>date('Y-m-d H:i:s')]);
    $s::insert('contacts', ['entities_id'=>999999,'users_id'=>$uid,'chat_id'=>'628123456780@c.us']);
    $s::event($foreign, 'finish', ['note'=>'FOREIGN ENTITY']);
    putenv('ITREQUEST_BRIDGE_TOKEN=local-fixture-token-00000000000000'); putenv('ITREQUEST_BRIDGE_ENTITY=0');
    $_SERVER['REQUEST_METHOD']='GET'; $_SERVER['HTTP_AUTHORIZATION']='Bearer local-fixture-token-00000000000000';
    ob_start(); require dirname(__DIR__) . '/front/wa-feed.php'; $json=ob_get_clean();
    $feed=json_decode($json,true,512,JSON_THROW_ON_ERROR);
    if (count($feed['events']) !== 1 || $feed['events'][0]['action'] !== 'finish' || str_contains($json,'SECRET') || str_contains($json,'private')) { throw new RuntimeException('Feed isolation failed'); }
    echo "PASS: opt-in entity-scoped WA feed, verified contact and no private payload.\n";
} finally { $DB->rollBack(); }
