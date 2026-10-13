"""Owned local inputs, never arbitrary paths or remote sources."""
from pathlib import Path
import tempfile
import shutil

MAX_FILE = 256 * 1024 * 1024
MAX_TOTAL = 512 * 1024 * 1024


class Workspaces:
    def __init__(self):
        self.directory = tempfile.TemporaryDirectory(prefix='lain42-subtitle-studio-')
        self.root = Path(self.directory.name).resolve()
        self.items = {}

    def new(self, identifier):
        if len(self.items) >= 5:
            raise ValueError('最多保留 5 组视频，请先保存成果并清空')
        root = self.root / identifier
        (root / 'input').mkdir(parents=True)
        (root / 'output').mkdir()
        item = {'id': identifier, 'root': root, 'videos': []}
        self.items[identifier] = item
        return item

    def get(self, identifier):
        if identifier not in self.items:
            raise ValueError('工作区不存在，请重新选择文件')
        return self.items[identifier]

    def delete(self, identifier):
        shutil.rmtree(self.get(identifier)['root'])
        del self.items[identifier]

    def close(self):
        self.directory.cleanup()
