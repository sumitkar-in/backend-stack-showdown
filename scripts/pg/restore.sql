-- run against database "postgres" with all apps stopped
DROP DATABASE IF EXISTS sensorpulse WITH (FORCE);
CREATE DATABASE sensorpulse TEMPLATE sensorpulse_tpl OWNER bench;
CHECKPOINT;
