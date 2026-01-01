# BeamState TODO List

## Features to Implement

### Monitoring & Data Collection
- [ ] **SNMP Support** - Add SNMP polling capability for network devices
- [ ] **Log to InfluxDB and/or Logfile** - Make logging destination configurable
- [ ] **Logfile Retention Setting** - Add configurable retention policy for JSON logs

### Configuration UI
- [ ] **Edit nodes and show selected protocol** - Add protocol selection to node edit form  
- [ ] **InfluxDB Config in UI** - Add InfluxDB connection settings to configuration page
- [ ] **Max Retries Config** - Expose `max_retries` setting in UI (currently only in config.json)
- [ ] **Ping Timeout Config** - Expose ping timeout setting in UI (currently hardcoded to 5000ms)
- [ ] **SNMP Timeout Config** - Expose SNMP timeout setting in UI (currently hardcoded to 5000ms)
- [ ] **SNMP Community Config** - Expose SNMP community setting in UI (currently only in config.json)
- [ ] **SNMP Port Config** - Expose SNMP port setting in UI (currently only in config.json)
- [ ] **SNMP OID Config** - Expose SNMP OID setting in UI (currently only in config.json)
- [ ] **SNMP Version Config** - Expose SNMP version setting in UI (currently only in config.json)

### Dashboard
- [ ] **Collapseable groups** - Add collapseable groups in dashboard
- [ ] **Drag and drop nodes** - Add drag and drop functionality to move nodes in a group

### Notifications
- [ ] **Pushover Support** - Add Pushover integration for push notifications on node status changes

### UI/UX Improvements
- [ ] **Mobile Config Layout** - Fix node configuration table wrapping on mobile devices (too small)
- [ ] **Auto-fill Group Interval** - When selecting a group in node config, auto-populate the group's default interval

## Completed Features
- [x] Start/Pause functionality for nodes and groups
- [x] Ping failure retry logic with configurable max retries
- [x] Raw ping response logging
- [x] InfluxDB-ready data format
- [x] Transparent logo in UI
