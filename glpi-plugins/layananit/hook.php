<?php
function plugin_layananit_install() { return true; }
function plugin_layananit_uninstall() { return true; }

function plugin_layananit_format_portal_ticket(Ticket $ticket): void
{
    if (Session::getCurrentInterface() !== 'helpdesk' || !Session::getLoginUserID()) {
        return;
    }
    $input = &$ticket->input;
    if (!empty($input['_layananit_portal_ticket'])) {
        return;
    }
    require_once __DIR__ . '/inc/ticketformat.class.php';
    $requesters = array_filter(array_map('intval', (array) ($input['_users_id_requester'] ?? [])));
    foreach ($input['_actors']['requester'] ?? [] as $actor) {
        if (($actor['itemtype'] ?? '') === User::class && !empty($actor['items_id'])) {
            $requesters[] = (int) $actor['items_id'];
        }
    }
    $requester = (int) (reset($requesters) ?: Session::getLoginUserID());
    if ($requester !== (int) Session::getLoginUserID() && !(new User())->can($requester, READ)) {
        $requester = (int) Session::getLoginUserID();
    }
    $content = (string) ($input['content'] ?? '');
    $location = (int) ($input['locations_id'] ?? 0);
    $site = $location ? Dropdown::getDropdownName('glpi_locations', $location) : '';
    $fields = PluginLayananitTicketFormat::portalFields($requester, $site, $input['name'] ?? '', $content);
    $input['name'] = PluginLayananitTicketFormat::portalTitle($fields);
    $input['content'] = '[HELPDESK_PORTAL_V1]<br>' . $content;
    if (!$location) {
        $input['locations_id'] = PluginLayananitTicketFormat::locationId(
            $fields['site'], (int) ($input['entities_id'] ?? $_SESSION['glpiactive_entity'] ?? 0),
        );
    }
}
