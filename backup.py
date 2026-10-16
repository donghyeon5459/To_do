#!/usr/bin/env python3
"""data.json 을 날짜별 파일(todo-YYYY-MM-DD.json)로 백업 폴더에 복사합니다.

사용: python3 backup.py <백업 폴더> [보관 일수(기본 30)]
- 같은 날 다시 실행하면 그날 파일을 덮어씁니다.
- 보관 일수보다 오래된 todo-날짜.json 파일만 지웁니다. (다른 파일은 건드리지 않음)
"""
import datetime
import os
import re
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "data.json")
NAME = re.compile(r"^todo-(\d{4}-\d{2}-\d{2})\.json$")


def main():
    if len(sys.argv) < 2:
        sys.exit("사용법: backup.py <백업 폴더> [보관 일수]")
    dest = sys.argv[1]
    keep = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    if not os.path.isfile(SRC):
        sys.exit(f"백업할 데이터가 아직 없어요: {SRC}")
    if not os.path.isdir(dest):
        sys.exit(f"백업 폴더가 없어요: {dest}")

    today = datetime.date.today()
    target = os.path.join(dest, f"todo-{today.isoformat()}.json")
    fd, tmp = tempfile.mkstemp(dir=dest, prefix=".todo-", suffix=".tmp")
    os.close(fd)
    try:
        shutil.copyfile(SRC, tmp)
        os.replace(tmp, target)   # 반쯤 복사된 파일이 남지 않게 한 번에 교체
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)

    removed = 0
    for f in os.listdir(dest):
        m = NAME.match(f)
        if m and (today - datetime.date.fromisoformat(m.group(1))).days > keep:
            os.remove(os.path.join(dest, f))
            removed += 1
    print(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} 백업 완료: {target} (오래된 백업 {removed}개 삭제)", flush=True)


if __name__ == "__main__":
    main()
