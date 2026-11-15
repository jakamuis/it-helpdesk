<?php
function plugin_init_layananit()
{
    global $PLUGIN_HOOKS;
    $PLUGIN_HOOKS['csrf_compliant']['layananit'] = true;
    $path = parse_url($_SERVER['REQUEST_URI'] ?? '', PHP_URL_PATH) ?: '';
    if (str_ends_with($path, '/front/central.php')) { $_SESSION['layananit_workspace'] = false; }
    if (str_contains($path, '/plugins/layananit/front/index.php')) { $_SESSION['layananit_workspace'] = true; }
    if (!empty($_SESSION['layananit_workspace']) && ($_SESSION['glpiactiveprofile']['interface'] ?? '') === 'central') {
        $PLUGIN_HOOKS['add_javascript']['layananit'] = ['public/workspace.js'];
        $native = preg_match('~/front/(ticket(?:\.form)?|computer(?:\.form)?|monitor(?:\.form)?|printer(?:\.form)?|user(?:\.form)?)\.php$~', $path);
        $plugin = preg_match('~/plugins/(itrequest|providersla)/front/(index|report)\.php$~', $path);
        if (($native || $plugin) && !isset($_GET['display_type'])) {
            // Head styles apply before the first paint, before the async shell is mounted.
            $PLUGIN_HOOKS['add_css']['layananit'] = ['public/app.css', 'public/native-shell.css'];
        }
    }

    $PLUGIN_HOOKS['menu_toadd']['layananit'] = ['tools' => 'PluginLayananitMenu'];
}
function plugin_version_layananit()
{
    return ['name' => 'Layanan TI', 'version' => '0.1.0', 'author' => 'IT Helpdesk', 'license' => 'GPLv3+',
        'requirements' => ['glpi' => ['min' => '11.0.8', 'max' => '11.0.99']]];
}
