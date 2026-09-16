-- 故意违规的替身：这张表在 source-asset-inventory.md 里没有登记。
CREATE TABLE t_secret_audit (
    id INTEGER PRIMARY KEY,
    actor TEXT,
    action TEXT
);
