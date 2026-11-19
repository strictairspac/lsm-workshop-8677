export const ROLES={admin:'管理员',operator:'操作员',viewer:'观察员'};export const STATUSES={queued:'排队中',running:'合并中',passed:'Oracle 一致',failed:'执行失败'};export const OPERATIONS={put:'写入',delete:'墓碑删除'};
export const REDUCTION_STATUSES={queued:'排队中',running:'缩减中',done:'已证最短',exhausted:'额度用完',failed:'执行失败'};
export const FAULTS={drop_tombstones_in_tiered:'层级合并丢弃墓碑',keep_stale_version_in_tiered:'层级合并保留旧版本',read_oldest_version:'点查取最旧版本',drop_latest_in_final_compaction:'最终完整合并丢弃最新写'};
export const PHASES={before_final_compaction:'最终完整合并之前',after_final_compaction:'最终完整合并之后'};
