<?php
class PluginLayananitMenu extends CommonGLPI
{
    public static function getMenuName() { return 'Layanan TI'; }
    public static function getMenuContent()
    {
        return ['title' => self::getMenuName(), 'page' => '/plugins/layananit/front/index.php', 'icon' => 'ti ti-layout-dashboard'];
    }
}
