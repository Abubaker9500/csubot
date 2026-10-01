<?php
/**
 * Odin public_html door. The app itself runs on HPC1.
 *
 * Static .html files are not served in this userdir, so the landing page is
 * PHP. For the reverse-proxy setup instead, deploy proxy.php + .htaccess
 * (see README.md) — those route every path and ignore this file.
 */
$target = 'https://hpc1.csub.edu/ab-sayed/';

if (!headers_sent()) {
    header('Location: ' . $target, true, 302);
}
?>
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>CSUBot</title>
  <meta http-equiv="refresh" content="0; url=<?= htmlspecialchars($target, ENT_QUOTES) ?>"/>
  <style>
    body {
      font-family: Sora, system-ui, sans-serif;
      background: #f5f6f8;
      color: #0d1117;
      min-height: 100dvh;
      display: flex;
      align-items: center;
      justify-content: center;
      margin: 0;
    }
    .card {
      background: #fff;
      border: 1px solid #dde0e8;
      border-radius: 20px;
      padding: 40px;
      max-width: 420px;
      text-align: center;
    }
    h1 { color: #003087; margin: 0 0 8px; }
    h1 span { color: #FDB913; }
    a { color: #003087; font-weight: 600; }
    p { color: #6b7280; }
  </style>
</head>
<body>
  <div class="card">
    <h1>CSU<span>Bot</span></h1>
    <p>Chat runs on HPC1 (Ollama + Flask). Odin hosts this public link.</p>
    <p><a href="<?= htmlspecialchars($target, ENT_QUOTES) ?>">Open CSUBot</a></p>
    <p>Requires the campus network or VPN.</p>
  </div>
</body>
</html>
