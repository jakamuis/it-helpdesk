<?php
require_once __DIR__ . '/service.class.php';
class PluginItrequestAttachment
{
    public static function directory(): string
    {
        return GLPI_DOC_DIR . '/_plugins/itrequest';
    }
    public static function upload(int $id, array $input, array $file): void
    {
        global $DB;
        $path = null;
        $DB->beginTransaction();
        try {
            $DB->doQuery('SELECT id FROM ' . PluginItrequestService::PREFIX . 'requests WHERE id=' . $id . ' FOR UPDATE');
            $r = PluginItrequestService::get($id);
            $owner = (int) $r['users_id'] === PluginItrequestService::uid();
            $can = ($owner && in_array($r['status'], ['draft','revision','information'], true))
                || (PluginItrequestService::staff((int) $r['entities_id']) && in_array($r['status'], ['queued','processing','information'], true));
            if (!$can || (int) ($input['version'] ?? 0) !== (int) $r['version']) { throw new InvalidArgumentException('Upload tidak diizinkan atau halaman sudah berubah.'); }
            if (($file['error'] ?? UPLOAD_ERR_NO_FILE) !== UPLOAD_ERR_OK || !is_uploaded_file($file['tmp_name'] ?? '')) { throw new InvalidArgumentException('Pilih file yang valid; cek batas upload server.'); }
            $size = filesize($file['tmp_name']);
            if (!$size || $size > 10 * 1024 * 1024) { throw new InvalidArgumentException('Ukuran file harus 1 byte sampai 10 MB.'); }
            $mime = (new finfo(FILEINFO_MIME_TYPE))->file($file['tmp_name']);
            if (!in_array($mime, ['application/pdf','image/jpeg','image/png'], true)) { throw new InvalidArgumentException('Hanya PDF, JPG dan PNG yang diizinkan.'); }
            $name = mb_substr(basename(str_replace('\\', '/', (string) $file['name'])), 0, 200);
            $name = preg_replace('/[\x00-\x1f\x7f]/', '', $name);
            $dir = self::directory();
            if (!is_dir($dir) && !mkdir($dir, 0700, true) && !is_dir($dir)) { throw new RuntimeException('Penyimpanan lampiran tidak tersedia.'); }
            $key = bin2hex(random_bytes(24));
            $path = $dir . '/' . $key;
            if (!move_uploaded_file($file['tmp_name'], $path)) { throw new RuntimeException('Gagal menyimpan lampiran.'); }
            chmod($path, 0600);
            $aid = PluginItrequestService::insert('attachments', ['requests_id' => $id, 'users_id' => PluginItrequestService::uid(),
                'filename' => $name, 'storage_key' => $key, 'mime' => $mime, 'size' => $size, 'created_at' => date('Y-m-d H:i:s')]);
            PluginItrequestService::update('requests', ['version' => (int) $r['version'] + 1, 'updated_at' => date('Y-m-d H:i:s')], ['id' => $id]);
            PluginItrequestService::event($id, 'attachment', ['filename' => $name, 'attachments_id' => $aid]);
            $DB->commit();
        } catch (Throwable $e) {
            $DB->rollBack();
            if ($path && is_file($path)) { unlink($path); }
            throw $e;
        }
    }
}
