<?php
/**
 * Odin → HPC1 bridge.
 *
 * From Odin, test:
 *   curl -sS http://hpc1.csub.edu:5000/ab-sayed/health
 *
 * If that works, keep this upstream. If it fails, on HPC1 run:
 *   ssh -N -R 5000:127.0.0.1:5000 sayed@odin.cs.csub.edu
 * and set upstream to http://127.0.0.1:5000
 */
return [
    'upstream'     => 'http://hpc1.csub.edu:5000',
    'flask_prefix' => '/ab-sayed',
];
