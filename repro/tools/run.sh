#!/bin/sh
# Start one worker per shard in tmux; each appends to results/shard<k>.jsonl.
cd /home/runner/work
mkdir -p repos logs results gopath
for f in shards/shard*.json; do
  k=$(basename $f .json)
  tmux new-session -d -s $k "RESOLVER=/home/runner/work/osv-resolver python3 -I tools/gochain.py /home/runner/work $f results/$k.jsonl > results/$k.log 2>&1"
done
tmux ls
