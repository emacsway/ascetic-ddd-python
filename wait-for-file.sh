#!/bin/sh

: ${SLEEP_LENGTH:=2}

wait_for_file() {
  stdbuf -i0 -o0 -e0 echo -n "Waiting for file $1..."
  while [ ! -f $1 ]; do stdbuf -i0 -o0 -e0 echo -n '.'; sleep $SLEEP_LENGTH; done
  echo ""
}

for var in "$@"
do
  wait_for_file $var
done
