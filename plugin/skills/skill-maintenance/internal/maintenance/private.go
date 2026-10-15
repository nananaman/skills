package maintenance

import (
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"syscall"
)

// canonical resolves existing symlinks even when the final output does not exist.
func canonical(path string) (string, error) {
	path, err := filepath.Abs(path)
	if err != nil {
		return "", err
	}
	if resolved, err := filepath.EvalSymlinks(path); err == nil {
		return resolved, nil
	} else if !errors.Is(err, os.ErrNotExist) {
		return "", err
	}
	parent := filepath.Dir(path)
	if parent == path {
		return path, nil
	}
	resolved, err := canonical(parent)
	if err != nil {
		return "", err
	}
	return filepath.Join(resolved, filepath.Base(path)), nil
}
func within(path, root string) bool {
	relative, err := filepath.Rel(root, path)
	return err == nil && relative != ".." && !strings.HasPrefix(relative, ".."+string(filepath.Separator))
}

// PrivateDirectory creates a fresh output outside all Git checkouts and metadata.
func PrivateDirectory(path, repo string) error {
	resolved, err := canonical(path)
	if err != nil {
		return err
	}
	repository, err := canonical(repo)
	if err != nil {
		return err
	}
	if within(resolved, repository) {
		return errors.New("private output must be outside improvement repository")
	}
	for parent := resolved; ; parent = filepath.Dir(parent) {
		if filepath.Base(parent) == ".git" {
			return errors.New("private output must be outside Git metadata")
		}
		if _, err := os.Stat(filepath.Join(parent, ".git")); err == nil {
			return errors.New("private output must be outside every Git checkout")
		} else if !errors.Is(err, os.ErrNotExist) {
			return err
		}
		if filepath.Dir(parent) == parent {
			break
		}
	}
	if err := os.MkdirAll(filepath.Dir(path), 0700); err != nil {
		return err
	}
	if err := os.Mkdir(path, 0700); err != nil {
		return err
	}
	return os.Chmod(path, 0700)
}
func openSource(path string) (*os.File, error) {
	fd, err := syscall.Open(path, syscall.O_RDONLY|syscall.O_NOFOLLOW, 0)
	if err != nil {
		return nil, &os.PathError{Op: "open", Path: path, Err: err}
	}
	return os.NewFile(uintptr(fd), path), nil
}
func createPrivate(path string) (*os.File, error) {
	fd, err := syscall.Open(path, syscall.O_WRONLY|syscall.O_CREAT|syscall.O_EXCL|syscall.O_NOFOLLOW, 0600)
	if err != nil {
		return nil, &os.PathError{Op: "open", Path: path, Err: err}
	}
	return os.NewFile(uintptr(fd), path), nil
}
func writeJSON(path string, value any) error {
	f, err := createPrivate(path)
	if err != nil {
		return err
	}
	encoder := json.NewEncoder(f)
	encoder.SetEscapeHTML(false)
	encoder.SetIndent("", "  ")
	err = encoder.Encode(value)
	closeErr := f.Close()
	if err != nil {
		return err
	}
	return closeErr
}
