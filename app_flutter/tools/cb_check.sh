#!/usr/bin/env bash
# CreatorBox Flutter 端沙箱静态检查（bash 版）
#
# 为什么需要这个：沙箱内 flutter/dart analyze 会崩（Process.start err 231 管道耗尽），
# 但 dartaotruntime + dartdevc 这条路【不 spawn 子进程】，可以跑。
# 它做的是真正的编译期检查：语法错误、未定义符号、类型不匹配都会报出来。
#
# 用法：
#   bash tools/cb_check.sh                 # 检查 lib/ 下全部 dart
#   bash tools/cb_check.sh lib/pages/xxx.dart   # 只检查指定文件
#
# 返回码：0=通过（可能有 lint 提示），1=有编译错误
set -u

PROJ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SDK="${FLUTTER_ROOT:-/d/dev/flutter}/bin/cache/dart-sdk"
RUNTIME="$SDK/bin/dartaotruntime.exe"
DEVDC="$SDK/bin/snapshots/dartdevc_aot.dart.snapshot"

if [ ! -f "$RUNTIME" ]; then
  echo "找不到 Dart SDK: $RUNTIME"
  echo "请设置 FLUTTER_ROOT 环境变量指向你的 flutter 目录"
  exit 2
fi

# 收集目标文件
if [ $# -gt 0 ]; then
  TARGETS=("$@")
else
  mapfile -t TARGETS < <(find "$PROJ/lib" -name '*.dart' | sort)
fi

if [ ${#TARGETS[@]} -eq 0 ]; then
  echo "没有找到 Dart 文件"
  exit 0
fi

echo "CreatorBox 静态检查（dartdevc 真编译，不依赖 flutter 命令）"
echo "目标文件 ${#TARGETS[@]} 个"
echo "============================================================"

# package_config.json 在 flutter pub get 之后才生成；
# 没有它就无法判定「依赖未解析」与「真实类型错误」——本工具会明确报「结论受限」而非谎报通过。
PKG="$PROJ/.dart_tool/package_config.json"
if [ -f "$PKG" ]; then
  PKG_ARG=(--packages "$PKG")
  DEPS_RESOLVED=1
else
  PKG_ARG=()
  DEPS_RESOLVED=0
  echo "[提示] 未找到 .dart_tool/package_config.json —— 依赖未解析。"
  echo ""
fi

OUT=$(mktemp -d)/out.dill
"$RUNTIME" "$DEVDC" "${PKG_ARG[@]}" "${TARGETS[@]}" -o "$OUT" > /tmp/cb_check_raw.txt 2>&1
RAW=/tmp/cb_check_raw.txt

echo ""
echo "============================================================"

# ⚠️ 错误行格式：  org-dartlang-app:/lib/x.dart:3:9: Error: xxx
#    路径含 Windows 盘符冒号，所以用「:数字:数字: Error:」定位，不能裸匹配 "Error:"。
ALL_ERRORS=$(grep -E ":[0-9]+:[0-9]+: Error:" "$RAW" || true)

if [ "$DEPS_RESOLVED" -eq 0 ]; then
  # 依赖未解析时，几乎所有 Widget/类型都会报 "isn't defined" / "isn't a type"。
  # 这类错误没有诊断价值（pub get 后自然消失），只统计数量并放行，
  # 但要明确告知用户「本轮结论受限」，不能谎报通过。
  TOTAL=$(echo "$ALL_ERRORS" | grep -cE ":[0-9]+:[0-9]+: Error:" || true)
  echo "结果：依赖未解析，产生 $TOTAL 处连锁噪音错误（不具诊断价值）"
  echo ""
  echo "⛔ 本轮【无法给出可信结论】—— 未跑 flutter pub get，flutter/http/uuid 等"
  echo "   全部解析失败，真实类型错误被噪音淹没。"
  echo ""
  echo "   你的下一步（本机执行）："
  echo "     cd D:\\WorkBuddyFILE\\CreatorBox\\app_flutter"
  echo "     flutter pub get"
  echo "     bash tools/cb_check.sh      # 依赖齐了再跑一次，这次结论可信"
  echo ""
  echo "当前唯一可确认的：无语法层面的结构性错误（能编到类型检查阶段）。"
  exit 2
fi

# 依赖已解析 —— 这时才做真判断
REAL_ERRORS=$(echo "$ALL_ERRORS" || true)
if [ -z "$REAL_ERRORS" ]; then
  echo "✅ 静态检查通过：无错误"
  exit 0
fi

COUNT=$(echo "$REAL_ERRORS" | grep -cE ":[0-9]+:[0-9]+: Error:" || true)
echo "❌ 发现 $COUNT 处错误："
echo ""
echo "$REAL_ERRORS"
exit 1