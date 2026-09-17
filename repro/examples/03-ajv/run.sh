#!/bin/sh
# reproducible: delete one line ("type": "integer") from the schema and see if the gate still rejects.
# run from anywhere:   sh 03-ajv/run.sh
cd "$(dirname "$0")" || exit 1

echo "[1] original schema + valid data          (expect exit 0)"
ajv validate --spec=draft2020 -s ./schema.json -d ./data_ok.json
echo "    -> exit $?"
echo
echo "[2] original schema + invalid data        (expect non-zero)"
ajv validate --spec=draft2020 -s ./schema.json -d ./data_bad.json
echo "    -> exit $?"
echo
echo "[3] ONE LINE DELETED + same invalid data  (the whole experiment)"
ajv validate --spec=draft2020 -s ./schema_mutated.json -d ./data_bad.json
echo "    -> exit $?"
