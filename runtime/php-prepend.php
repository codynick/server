<?php
// Each container belongs to one authenticated account. Never share PHP sessions
// between containers or forward the host application's authentication cookie.
ini_set('session.save_path', '/tmp');
session_id('workspace');
