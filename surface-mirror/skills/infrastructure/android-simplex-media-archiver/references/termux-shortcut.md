# Termux Shortcut for the SimpleX Video Watcher

Create a one-tap launcher inside Termux:

```sh
mkdir -p ~/.shortcuts
cat > ~/.shortcuts/start-video-watcher << 'EOL'
#!/data/data/com.termux/files/usr/bin/sh
cd /data/data/com.termux/files/home
nohup /data/data/com.termux/files/usr/bin/python simplex_phone_watcher.py \
  > /sdcard/SimplexVideos/watcher.out 2>&1 &
echo $! > /sdcard/SimplexVideos/watcher.pid
EOL
chmod +x ~/.shortcuts/start-video-watcher
```

Launch from the Termux "Shortcuts" menu or by running the script directly.

The watcher runs as a background root process and survives Termux being closed.
