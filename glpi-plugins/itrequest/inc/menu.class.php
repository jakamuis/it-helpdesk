<?php
class PluginItrequestMenu extends CommonGLPI
{
    public static function getTypeName($nb = 0) { return 'Request IT'; }
    public static function getMenuName() { return 'Request IT'; }
    public static function getMenuContent()
    {
        return ['title' => 'Request IT', 'page' => Plugin::getWebDir('itrequest') . '/front/index.php',
            'icon' => 'ti ti-clipboard-check'];
    }
}
