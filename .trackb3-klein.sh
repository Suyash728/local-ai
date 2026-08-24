#!/usr/bin/env bash
# FLUX.2-klein-9B NVFP4. Gated repo, license accepted 2026-08-24.
# FLUX Non-Commercial License - same family as FLUX.1-dev already installed.
LOG=/home/suyash/AI/.trackb3-klein.log
: > "$LOG"
cd /home/suyash/AI
set -a; . ./.env 2>/dev/null; set +a
export HF_HOME=/home/suyash/AI/models/hf
export HF_HUB_DISABLE_XET=1
export HF_HUB_DOWNLOAD_TIMEOUT=60
M=/home/suyash/AI/models/comfyui
FAILED=0

get() { # repo remote-path destdir note
  echo "" >> "$LOG"; echo ">>> [$(date +%H:%M:%S)] $1 :: $2  ($4)" >> "$LOG"
  hf download "$1" "$2" --local-dir "$3" >> "$LOG" 2>&1
  if [ $? -eq 0 ]; then echo "<<< [$(date +%H:%M:%S)] OK" >> "$LOG"
  else echo "<<< [$(date +%H:%M:%S)] FAILED" >> "$LOG"; FAILED=$((FAILED+1)); fi
}

echo "=== klein-9B download started $(date -Is) ===" >> "$LOG"
get black-forest-labs/FLUX.2-klein-9b-nvfp4 flux-2-klein-9b-nvfp4.safetensors "$M" "5.37 GiB"
get Comfy-Org/flux2-klein-9b split_files/text_encoders/qwen_3_8b_fp4mixed.safetensors "$M" "6.34 GiB"
get Comfy-Org/flux2-klein-9b split_files/vae/flux2-vae.safetensors "$M" "0.31 GiB"

# flatten: transformer lands at repo root, others under split_files/
mv -n "$M/flux-2-klein-9b-nvfp4.safetensors" "$M/diffusion_models/" 2>>"$LOG"
mv -n "$M/split_files/text_encoders/qwen_3_8b_fp4mixed.safetensors" "$M/text_encoders/" 2>>"$LOG"
mv -n "$M/split_files/vae/flux2-vae.safetensors" "$M/vae/" 2>>"$LOG"
rm -rf "$M/split_files" "$M/.cache"

echo "" >> "$LOG"
echo "=== finished $(date -Is) - failures: $FAILED ===" >> "$LOG"
ls -la "$M/diffusion_models" "$M/text_encoders" "$M/vae" >> "$LOG" 2>&1
df -h / | tail -1 | sed 's/^/    disk: /' >> "$LOG"
exit $FAILED
