<?php
// Stable plugin entry point; an optional web-server alias /request can target this file.
require_once dirname(__DIR__, 3) . '/inc/includes.php';
Session::checkLoginUser();
if (!Plugin::isPluginActive('itrequest') || !Plugin::isPluginActive('layananit')) {
    throw new Glpi\Exception\Http\AccessDeniedHttpException();
}
Html::redirect(Plugin::getWebDir('itrequest') . '/front/index.php?tab=new');
