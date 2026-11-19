ROLES=('admin','operator','viewer')
STATUSES=('queued','running','passed','failed')
OPERATIONS=('put','delete')
# Simulated faults for the reduction workshop; normal trials never pass one.
FAULTS=('drop_tombstones_in_tiered','keep_stale_version_in_tiered','read_oldest_version','drop_latest_in_final_compaction')
FAILURE_PHASES=('before_final_compaction','after_final_compaction')
REDUCTION_STATUSES=('queued','running','done','exhausted','failed')
