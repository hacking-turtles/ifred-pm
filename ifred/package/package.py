from StringIO import StringIO

import os
import json
import requests
import zipfile

from ..config import g

sess = requests.Session()


class Package(object):
    def __init__(self, name, path, version):
        self.name = name
        self.path = path
        self.version = version

    def install(self):
        raise NotImplementedError

    def remove(self):
        raise NotImplementedError

    def fetch(self, url):
        raise NotImplementedError

    @staticmethod
    def validate_info(info):
        assert 'name' in info
        assert 'version' in info
        assert 'entry' in info

        assert isinstance(info['entry'], basestring) or isintance(info['entry'], dict) \
            and supported_platforms.issubset(info['entry'].keys()) \
            and all(isinstance(x, basestring) for x in info['entry'].values())

    def __repr__(self):
        return '<%s name=%r path=%r version=%r>' % (self.__class__.__name__, self.name, self.path, self.version)


class LocalPackage(Package):
    def __init__(self, name, path, version):
        super(LocalPackage, self).__init__(name, path, version)

    def remove(self):
        with open(os.path.join(self.path, '.removed'), 'wb') as f:
            pass

    def fetch(self, url):
        return open(url, 'rb').read()

    def load(self):
        import ida_loader
        entry = os.path.join(self.path, self.info()['entry'])
        print 'Loading', `entry`
        ida_loader.load_plugin(str(entry))

    def info(self):
        with open(os.path.join(self.path, 'info.json'), 'rb') as f:
            return json.load(f)

    @staticmethod
    def by_name(name, prefix=None):
        if prefix is None:
            prefix = g['path']['plugins']

        path = os.path.join(prefix, name)

        # filter removed package
        removed = os.path.join(path, '.removed')
        if os.path.isfile(removed):
            return None

        info_json = os.path.join(path, 'info.json')
        if not os.path.isfile(info_json):
            print 'Warning: info.json is not found at', path
            return None
        with open(info_json, 'rb') as f:
            info = json.load(f)
            result = LocalPackage(name=name if 'title' not in info or not info['title'].strip() else info['title'], path=path, version=info['version'])
        return result

    @staticmethod
    def all():
        prefix = g['path']['plugins']

        l = os.listdir(prefix)
        l = filter(lambda x: os.path.isdir(os.path.join(prefix, x)), l)
        l = map(lambda x: LocalPackage.by_name(x), l)
        l = filter(lambda x: x, l)
        return l


class InstallablePackage(Package):
    def __init__(self, name, path, version, base):
        super(InstallablePackage, self).__init__(name, path, version)
        self.base = base

    def install(self):
        print 'Downloading...'
        data = self.fetch(self.base + self.path)
        io = StringIO(data)

        print 'Validating...'
        install_path = os.path.join(
            g['path']['plugins'],
            self.path
        )

        with zipfile.ZipFile(io, 'r') as f:
            with f.open('info.json') as j:
                info = json.load(j)
                Package.validate_info(info)
            f.extractall(install_path)

            print 'Extracting into %r...' % install_path
            assert os.path.isfile(os.path.join(install_path, 'info.json'))

        removed = os.path.join(install_path, '.removed')
        if os.path.isfile(removed):
            os.unlink(removed)

        pkg = LocalPackage(str(self.name), install_path, self.version)
        pkg.load()

        return pkg

    def fetch(self, url):
        r = sess.get(url)
        assert r.status_code / 100 == 2, '2xx status required'
        return r.content