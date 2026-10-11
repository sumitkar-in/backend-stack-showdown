-- run against database "postgres"; sensorpulse must have no other connections
DROP DATABASE IF EXISTS sensorpulse_tpl;
CREATE DATABASE sensorpulse_tpl TEMPLATE sensorpulse;
ALTER DATABASE sensorpulse_tpl WITH ALLOW_CONNECTIONS false;
