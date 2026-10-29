<?php
/** Pure elapsed-time calculations. All stored instants are Unix seconds. */
final class PluginProviderslaClock
{
    public static function parse(string $value): int
    {
        $value = str_replace('T', ' ', trim($value));
        $date = DateTimeImmutable::createFromFormat('!Y-m-d H:i', $value, new DateTimeZone('Asia/Jakarta'));
        if (!$date || $date->format('Y-m-d H:i') !== $value) {
            throw new InvalidArgumentException('Tanggal/jam tidak valid. Gunakan waktu Asia/Jakarta.');
        }
        return $date->getTimestamp();
    }
    public static function date(?int $epoch, string $format = 'd-m-Y H:i'): string
    {
        return $epoch === null ? '—' : (new DateTimeImmutable('@' . $epoch))
            ->setTimezone(new DateTimeZone('Asia/Jakarta'))->format($format);
    }
    public static function target(string $hours): ?int
    {
        $hours = trim($hours);
        if ($hours === '') {
            return null;
        }
        if (!preg_match('/^\d{1,4}(\.\d{1,2})?$/D', $hours) || (float) $hours <= 0 || (float) $hours > 8760) {
            throw new InvalidArgumentException('Target harus lebih dari 0 sampai 8760 jam, maksimal 2 angka desimal.');
        }
        return (int) round((float) $hours * 3600);
    }
    public static function metrics(array $row, int $snapshot): array
    {
        $start = (int) $row['transferred_epoch'];
        $end = isset($row['restored_epoch']) ? (int) $row['restored_epoch'] : $snapshot;
        if ($end < $start) {
            throw new InvalidArgumentException('Waktu akhir mendahului waktu pengalihan.');
        }
        $target = isset($row['target_seconds']) ? (int) $row['target_seconds'] : null;
        $deadline = $target === null ? null : $start + $target;
        $status = !empty($row['is_void']) ? 'Dibatalkan'
            : ($target === null ? 'Tanpa Target'
                : (isset($row['restored_epoch'])
                    ? ($end <= $deadline ? 'Memenuhi' : 'Melanggar')
                    : ($end <= $deadline ? 'Berjalan, belum lewat' : 'Berjalan, terlambat')));
        return ['seconds' => $end - $start, 'deadline' => $deadline, 'status' => $status];
    }
    public static function duration(int $seconds): string
    {
        return sprintf('%dj %02dm %02dd', intdiv($seconds, 3600), intdiv($seconds % 3600, 60), $seconds % 60);
    }
    public static function csv(string $value): string
    {
        return preg_match('/^[\s]*[=+@\-\t\r\n]/u', $value) ? "'" . $value : $value;
    }
}
