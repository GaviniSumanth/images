package main

import (
	"fmt"
	"os"
	"path/filepath"
	"syscall"
)

const (
	binaryPath   = "/usr/bin/qbittorrent-nox"
	configDir    = "/config"
	configPath   = "/config/qBittorrent/config/qBittorrent.conf"
	templatePath = "/usr/share/qbittorrent/qBittorrent.conf"
)

func main() {
	entries, err := os.ReadDir(configDir)
	if err != nil && !os.IsNotExist(err) {
		fatal("read config directory", err)
	}

	if len(entries) == 0 {
		if err := os.MkdirAll(filepath.Dir(configPath), 0o755); err != nil {
			fatal("create config directory", err)
		}

		contents, err := os.ReadFile(templatePath)
		if err != nil {
			fatal("read default config", err)
		}
		if err := os.WriteFile(configPath, contents, 0o644); err != nil {
			fatal("seed default config", err)
		}
	}

	args := append([]string{binaryPath}, os.Args[1:]...)
	if err := syscall.Exec(binaryPath, args, os.Environ()); err != nil {
		fatal("exec qBittorrent", err)
	}
}

func fatal(action string, err error) {
	fmt.Fprintf(os.Stderr, "qbittorrent-entrypoint: %s: %v\n", action, err)
	os.Exit(1)
}
