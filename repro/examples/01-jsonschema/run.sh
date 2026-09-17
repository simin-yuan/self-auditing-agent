#!/bin/sh
# reproducible: delete one line ("type": "integer") from the schema and see if the gate still rejects.
# run from anywhere:   sh 01-jsonschema/run.sh
cd "$(dirname "$0")" || exit 1

echo "[1] original schema + valid data          (expect exit 0)"
python -m jsonschema --instance ./data_ok.json ./schema.json
echo "    -> exit $?"
echo
echo "[2] original schema + invalid data        (expect non-zero)"
python -m jsonschema --instance ./data_bad.json ./schema.json
echo "    -> exit $?"
echo
echo "[3] ONE LINE DELETED + same invalid data  (the whole experiment)"
python -m jsonschema --instance ./data_bad.json ./schema_mutated.json
echo "    -> exit $?"
