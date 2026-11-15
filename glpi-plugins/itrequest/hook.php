<?php
function plugin_itrequest_install()
{
    global $DB;
    $tables = [
        'requests' => '`approved_at` datetime DEFAULT NULL, `entities_id` int unsigned NOT NULL, `users_id` int unsigned NOT NULL,
            `approvers_id` int unsigned NOT NULL DEFAULT 0, `status` varchar(30) NOT NULL,
            `version` int unsigned NOT NULL DEFAULT 1, `payload` longtext NOT NULL,
            `assigned_id` int unsigned NOT NULL DEFAULT 0, `target_date` varchar(10) NOT NULL DEFAULT \'\',
            `created_at` datetime NOT NULL, `updated_at` datetime NOT NULL,
            KEY `owner` (`users_id`), KEY `approver` (`approvers_id`), KEY `entity_status` (`entities_id`,`status`)',
        'attachments' => '`requests_id` int unsigned NOT NULL, `users_id` int unsigned NOT NULL,
            `filename` varchar(255) NOT NULL, `storage_key` varchar(64) NOT NULL, `mime` varchar(100) NOT NULL,
            `size` int unsigned NOT NULL, `created_at` datetime NOT NULL, KEY `request_files` (`requests_id`)',
        'events' => '`requests_id` int unsigned NOT NULL, `users_id` int unsigned NOT NULL,
            `action` varchar(40) NOT NULL, `details` longtext NOT NULL, `created_at` datetime NOT NULL,
            KEY `history` (`requests_id`,`id`)',
        'mappings' => '`entities_id` int unsigned NOT NULL, `users_id` int unsigned NOT NULL,
            `approvers_id` int unsigned NOT NULL, UNIQUE KEY `mapping` (`entities_id`,`users_id`)',
        'managers' => '`entities_id` int unsigned NOT NULL, `users_id` int unsigned NOT NULL, UNIQUE KEY `manager` (`entities_id`,`users_id`)',
        'contacts' => '`entities_id` int unsigned NOT NULL, `users_id` int unsigned NOT NULL, `chat_id` varchar(40) NOT NULL, `after_event_id` int unsigned NOT NULL DEFAULT 0, UNIQUE KEY `contact` (`entities_id`,`users_id`)',
        'staff' => '`entities_id` int unsigned NOT NULL, `users_id` int unsigned NOT NULL,
            UNIQUE KEY `staff` (`entities_id`,`users_id`)',
    ];
    foreach ($tables as $name => $columns) {
        $DB->doQuery("CREATE TABLE IF NOT EXISTS `glpi_plugin_itrequest_$name` (
            `id` int unsigned NOT NULL AUTO_INCREMENT, $columns, PRIMARY KEY (`id`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");
    }
    if (!$DB->fieldExists('glpi_plugin_itrequest_contacts', 'after_event_id')) {
        $DB->doQuery('ALTER TABLE glpi_plugin_itrequest_contacts ADD after_event_id int unsigned NOT NULL DEFAULT 0');
    }
    if (!$DB->fieldExists('glpi_plugin_itrequest_requests', 'approved_at')) {
        $DB->doQuery('ALTER TABLE glpi_plugin_itrequest_requests ADD approved_at datetime DEFAULT NULL');
    }
    foreach (['requests' => ['directors_id' => 'int unsigned NOT NULL DEFAULT 0', 'manager_approved_at' => 'datetime DEFAULT NULL'],
        'mappings' => ['directors_id' => 'int unsigned NOT NULL DEFAULT 0']] as $table => $columns) {
        foreach ($columns as $column => $definition) {
            if (!$DB->fieldExists('glpi_plugin_itrequest_' . $table, $column)) {
                $DB->doQuery("ALTER TABLE glpi_plugin_itrequest_$table ADD `$column` $definition");
            }
        }
    }
    return true;
}
function plugin_itrequest_uninstall() { return true; } // Preserve requests and audit history.
