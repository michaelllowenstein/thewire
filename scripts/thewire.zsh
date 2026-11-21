# Source this file after activating the TheWire virtual environment or installing tw.
function twc(){ tw tool run clc -- "$@"; }
function two(){ tw tool run onboarded -- "$@"; }
function twdb(){ tw tool run dbscaffold -- "$@"; }
function twrw(){ tw tool run reworked -- "$@"; }
function twstatus(){ tw time status; }
