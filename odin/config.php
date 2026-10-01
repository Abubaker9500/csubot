<?php
/**
 * Where Flask lives, in priority order.
 *
 * 127.0.0.1:5000  = the SSH tunnel kept open by tunnel.sh (works today)
 * hpc1.csub.edu:5000 = direct, only after the admin opens Odin -> HPC1 TCP 5000
 *
 * proxy.php probes /health and uses the first one that answers, so you can
 * leave both here. Delete the tunnel entry once the firewall is open.
 */
return [
    'upstreams' => [
        // Through Alberto's NGINX. Odin can reach HPC1 on 443, so this needs
        // no tunnel and no firewall change.
        'https://hpc1.csub.edu',
        // SSH tunnel kept alive by tunnel.sh.
        'http://127.0.0.1:5000',
        // Direct to gunicorn, only if the admin opens Odin -> HPC1 TCP 5000.
        'http://hpc1.csub.edu:5000',
    ],
    'flask_prefix' => '/ab-sayed',

    // Set false only if HPC1 serves a self-signed certificate.
    'verify_tls' => true,

    // Shown if no upstream answers.
    'fallback_url' => 'https://hpc1.csub.edu/ab-sayed/',
];
