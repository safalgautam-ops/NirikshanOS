-- Three more categories needed to cover the full tool list across all 4
-- tiers - network tools, Windows-artifact tools, and threat-hunting/EDR
-- tools didn't fit any of the original 6.
INSERT INTO `categories` (`id`, `name`, `description`, `sort_order`) VALUES
  ('network_forensics',  'Network Forensics',    'Packet capture and network traffic analysis tools', 6),
  ('windows_artifacts',  'Windows Artifacts',    'Registry, event log, and Windows-specific artifact analysis tools', 7),
  ('threat_hunting_edr', 'Threat Hunting & EDR', 'Remote endpoint forensics, EDR, and fast triage/hunting tools', 8)
ON DUPLICATE KEY UPDATE `name` = VALUES(`name`);
