<?php
/**
 * Reverse-proxy public_html → Flask on HPC1.
 * Browser stays on cs.csub.edu so login cookies work.
 */
$config = require __DIR__ . '/config.php';
$flaskPrefix = '/' . trim($config['flask_prefix'], '/');

$candidates = $config['upstreams'] ?? [$config['upstream'] ?? 'http://127.0.0.1:5000'];
$candidates = array_map(function ($u) { return rtrim($u, '/'); }, (array) $candidates);

/**
 * Pick the first upstream whose /health answers. Cached briefly so we do not
 * probe on every asset request.
 */
function csubot_pick_upstream(array $candidates, $flaskPrefix, $verifyTls) {
    $cache = sys_get_temp_dir() . '/csubot_upstream_' . md5(implode('|', $candidates)) . '.txt';
    if (is_readable($cache) && (time() - filemtime($cache)) < 30) {
        $cached = trim((string) file_get_contents($cache));
        if ($cached !== '' && in_array($cached, $candidates, true)) {
            return $cached;
        }
    }
    foreach ($candidates as $candidate) {
        $ch = curl_init($candidate . $flaskPrefix . '/health');
        curl_setopt_array($ch, [
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_CONNECTTIMEOUT => 2,
            CURLOPT_TIMEOUT        => 4,
            CURLOPT_SSL_VERIFYPEER => $verifyTls,
            CURLOPT_SSL_VERIFYHOST => $verifyTls ? 2 : 0,
        ]);
        $out = curl_exec($ch);
        $code = (int) curl_getinfo($ch, CURLINFO_HTTP_CODE);
        curl_close($ch);
        if ($code === 200 && is_string($out) && strpos($out, '"status"') !== false) {
            @file_put_contents($cache, $candidate);
            return $candidate;
        }
    }
    return null;
}

$verifyTls = (bool) ($config['verify_tls'] ?? true);
$upstream = csubot_pick_upstream($candidates, $flaskPrefix, $verifyTls);

if ($upstream === null) {
    $fallback = $config['fallback_url'] ?? '';
    http_response_code(503);
    header('Content-Type: text/html; charset=utf-8');
    echo '<!DOCTYPE html><html><head><meta charset="utf-8"><title>CSUBot is offline</title>';
    echo '<style>body{font-family:system-ui,sans-serif;background:#f5f6f8;color:#0d1117;display:flex;';
    echo 'min-height:100dvh;align-items:center;justify-content:center;margin:0}';
    echo '.card{background:#fff;border:1px solid #dde0e8;border-radius:20px;padding:40px;max-width:460px}';
    echo 'h1{color:#003087;margin:0 0 8px}h1 span{color:#FDB913}p{color:#6b7280}code{font-size:.9em}</style>';
    echo '</head><body><div class="card"><h1>CSU<span>Bot</span> is offline</h1>';
    echo '<p>The chat service on HPC1 is not answering right now.</p>';
    if ($fallback !== '') {
        echo '<p>You can try <a href="' . htmlspecialchars($fallback, ENT_QUOTES) . '">the HPC1 address</a> from a campus computer.</p>';
    }
    echo '<p>Owner checklist: <code>./run_hpc.sh</code> on HPC1, then <code>~/bin/csubot-tunnel.sh</code> on Odin.</p>';
    echo '</div></body></html>';
    exit;
}

$publicPrefix = rtrim(str_replace('\\', '/', dirname($_SERVER['SCRIPT_NAME'] ?? '')), '/');
if ($publicPrefix === '/' || $publicPrefix === '.') {
    $publicPrefix = '';
}

$https = (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off')
    || ((string)($_SERVER['SERVER_PORT'] ?? '') === '443');
$publicOrigin = ($https ? 'https' : 'http') . '://' . ($_SERVER['HTTP_HOST'] ?? 'localhost');

$path = parse_url($_SERVER['REQUEST_URI'] ?? '/', PHP_URL_PATH) ?: '/';
if ($publicPrefix !== '' && strpos($path, $publicPrefix) === 0) {
    $path = substr($path, strlen($publicPrefix)) ?: '/';
}
if ($path === '' || $path[0] !== '/') {
    $path = '/' . $path;
}
if ($path === '/proxy.php' || $path === '/index.php' || $path === '/config.php') {
    $path = '/';
}

$target = $upstream . $flaskPrefix . $path;
$query = $_SERVER['QUERY_STRING'] ?? '';
if ($query !== '') {
    $target .= '?' . $query;
}

$method = strtoupper($_SERVER['REQUEST_METHOD'] ?? 'GET');
$body = ($method === 'GET' || $method === 'HEAD') ? '' : file_get_contents('php://input');

$incoming = [];
if (function_exists('getallheaders')) {
    $incoming = getallheaders() ?: [];
} else {
    foreach ($_SERVER as $key => $value) {
        if (strpos($key, 'HTTP_') === 0) {
            $name = str_replace(' ', '-', ucwords(strtolower(str_replace('_', ' ', substr($key, 5)))));
            $incoming[$name] = $value;
        }
    }
    if (!empty($_SERVER['CONTENT_TYPE'])) {
        $incoming['Content-Type'] = $_SERVER['CONTENT_TYPE'];
    }
}
$reqHeaders = [];
foreach ($incoming as $name => $value) {
    $lname = strtolower($name);
    if (in_array($lname, ['host', 'connection', 'keep-alive', 'transfer-encoding', 'te', 'trailer', 'upgrade', 'content-length'], true)) {
        continue;
    }
    $reqHeaders[] = $name . ': ' . $value;
}
$reqHeaders[] = 'X-Forwarded-For: ' . ($_SERVER['REMOTE_ADDR'] ?? '');
$reqHeaders[] = 'X-Forwarded-Proto: ' . ($https ? 'https' : 'http');
$reqHeaders[] = 'X-Forwarded-Host: ' . ($_SERVER['HTTP_HOST'] ?? '');
$reqHeaders[] = 'Expect:';

$stream = (strpos($path, '/chat') === 0);

function csubot_rewrite($text, $upstream, $flaskPrefix, $publicOrigin, $publicPrefix) {
    $replacements = [
        $upstream . $flaskPrefix => $publicOrigin . $publicPrefix,
        'http://127.0.0.1:5000' . $flaskPrefix => $publicOrigin . $publicPrefix,
        'http://localhost:5000' . $flaskPrefix => $publicOrigin . $publicPrefix,
        $flaskPrefix => $publicPrefix,
    ];
    return strtr($text, $replacements);
}

$respHeaders = [];
$ch = curl_init($target);
curl_setopt_array($ch, [
    CURLOPT_CUSTOMREQUEST  => $method,
    CURLOPT_HTTPHEADER     => $reqHeaders,
    CURLOPT_FOLLOWLOCATION => false,
    CURLOPT_TIMEOUT        => 120,
    CURLOPT_CONNECTTIMEOUT => 10,
    CURLOPT_HEADER         => false,
    CURLOPT_SSL_VERIFYPEER => $verifyTls,
    CURLOPT_SSL_VERIFYHOST => $verifyTls ? 2 : 0,
    CURLOPT_HEADERFUNCTION => function ($ch, $headerLine) use (&$respHeaders) {
        $len = strlen($headerLine);
        $parts = explode(':', $headerLine, 2);
        if (count($parts) === 2) {
            $respHeaders[strtolower(trim($parts[0]))][] = trim($parts[1]);
        }
        return $len;
    },
]);
if ($body !== '' && $body !== false) {
    curl_setopt($ch, CURLOPT_POSTFIELDS, $body);
}

if ($stream) {
    curl_setopt($ch, CURLOPT_WRITEFUNCTION, function ($ch, $data) {
        echo $data;
        if (function_exists('ob_flush')) {
            @ob_flush();
        }
        flush();
        return strlen($data);
    });
} else {
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
}

$status = 502;
$responseBody = '';
if ($stream) {
    http_response_code(200);
    header('Content-Type: application/x-ndjson');
    header('Cache-Control: no-cache');
    header('X-Accel-Buffering: no');
    $ok = curl_exec($ch);
    $status = (int) curl_getinfo($ch, CURLINFO_HTTP_CODE) ?: 502;
    curl_close($ch);
    if ($ok === false && $status === 502) {
        echo json_encode(['error' => 'Could not reach CSUBot on HPC1.']) . "\n";
    }
    exit;
}

$responseBody = curl_exec($ch);
$errno = curl_errno($ch);
$status = (int) curl_getinfo($ch, CURLINFO_HTTP_CODE);
$contentType = (string) curl_getinfo($ch, CURLINFO_CONTENT_TYPE);
curl_close($ch);

if ($errno || $responseBody === false) {
    @unlink(sys_get_temp_dir() . '/csubot_upstream_' . md5(implode('|', $candidates)) . '.txt');
    http_response_code(502);
    header('Content-Type: text/plain; charset=utf-8');
    echo "CSUBot proxy could not reach Flask on HPC1.\n";
    echo "On Odin run: curl -sS {$upstream}{$flaskPrefix}/health\n";
    exit;
}

http_response_code($status ?: 502);

$skip = ['connection', 'keep-alive', 'transfer-encoding', 'content-length', 'content-encoding'];
foreach ($respHeaders as $name => $values) {
    if (in_array($name, $skip, true)) {
        continue;
    }
    foreach ($values as $value) {
        if ($name === 'location') {
            $value = csubot_rewrite($value, $upstream, $flaskPrefix, $publicOrigin, $publicPrefix);
        } elseif ($name === 'set-cookie') {
            $value = preg_replace('/Path=\/ab-sayed/i', 'Path=' . ($publicPrefix === '' ? '/' : $publicPrefix), $value);
            $value = csubot_rewrite($value, $upstream, $flaskPrefix, $publicOrigin, $publicPrefix);
        }
        header($name . ': ' . $value, false);
    }
}

$rewriteTypes = ['text/html', 'text/css', 'text/javascript', 'application/javascript', 'application/json'];
$shouldRewrite = false;
foreach ($rewriteTypes as $type) {
    if (stripos($contentType, $type) !== false) {
        $shouldRewrite = true;
        break;
    }
}
if ($shouldRewrite) {
    $responseBody = csubot_rewrite($responseBody, $upstream, $flaskPrefix, $publicOrigin, $publicPrefix);
}

header('Content-Length: ' . strlen($responseBody));
echo $responseBody;
