#!/bin/sh
# reproducible: delete one line ("type": "integer") from the schema and see if the gate still rejects.
# run from anywhere:   sh 02-check-jsonschema/run.sh
cd "$(dirname "$0")" || exit 1

echo "[1] original schema + valid data          (expect exit 0)"
check-jsonschema --schemafile ./schema.json ./data_ok.json
echo "    -> exit $?"
echo
echo "[2] original schema + invalid data        (expect non-zero)"
check-jsonschema --schemafile ./schema.json ./data_bad.json
echo "    -> exit $?"
echo
echo "[3] ONE LINE DELETED + same invalid data  (the whole experiment)"
check-jsonschema --schemafile ./schema_mutated.json ./data_bad.json
echo "    -> exit $?"
