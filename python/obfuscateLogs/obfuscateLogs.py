#!/usr/bin/env python
"""obfuscate logs - version 2024-05-21a"""

import os
import gzip
import shutil
import re
import codecs
import tarfile

# command line arguments
import argparse
parser = argparse.ArgumentParser()
parser.add_argument('-l', '--logpath', type=str, required=True)
args = parser.parse_args()

logpath = args.logpath

if os.path.isdir(logpath) is False:
    print('logpath %s is not found' % logpath)
    exit(1)

ignore_paths = [
    '/td',
    '/tr',
    '/th',
    '/a',
    '/table',
    '/tbody',
    '/thead',
    '/tracez',
    '/flagz',
    '/statz',
    '/pulsez',
    '/master',
    '/head',
    '/script',
    '/font',
    '/css',
    '/javascript',
    '/html'
]


def obfuscatefile(root, filepath):
    filename = os.path.basename(filepath)
    if filename.startswith('xxx-'):
        return
    print(filepath)
    outfile = os.path.join(root, 'xxx-%s' % filename)
    with codecs.open(filepath, 'r', 'latin-1') as f_in:
        with codecs.open(outfile, 'w', 'latin-1') as f_out:
            for line in f_in:
                if '/' in line:
                    tags = ''.join(re.findall(r'(<.*?[\w:|\.|-|"|=]+>)', line))
                    lineparts = re.split('=|\"', line)
                    for linepart in lineparts:
                        paths = re.findall(r'(\/.*?[\w:|\.|-]+)', linepart)
                        paths = [p for p in paths if p not in tags and p not in [i for i in ignore_paths]]
                        for path in paths:
                            line = line.replace(path, '/xxx')
                f_out.write('%s' % line)
            f_out.close()
            f_in.close()
            os.remove(filepath)
            os.rename(outfile, filepath)


def gzfile(path):
    with open(path, 'rb') as f_in:
        with gzip.open('%s.gz' % path, 'wb') as f_out:
            shutil.copyfileobj(f_in, f_out)


def targzdirectory(path,name):
    with tarfile.open(name, "w:gz") as tarhandle:
        for root, dirs, files in os.walk(path):
            for f in files:
                fullname = os.path.join(root, f)
                relname = fullname.replace(path,'')
                tarhandle.add(os.path.join(root, f), arcname=relname)


def walkdir(thispath):
    for root, dirs, files in os.walk(thispath):
        for filename in sorted(files):
            filepath = os.path.join(root, filename)
            filename_short, file_extension = os.path.splitext(filename)
            if file_extension.lower() == '.gz':
                # unzip gz file
                unzippedfile = os.path.join(root, filename_short)
                with gzip.open(filepath, 'rb') as f_in:
                    with open(unzippedfile, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
                os.remove(filepath)
                unzipped_filename_short, unzipped_file_extension = os.path.splitext(unzippedfile)
                if unzipped_file_extension.lower() == '.tar':
                    # untar tar file
                    untarred_folder = unzippedfile[0:-4]
                    tar = tarfile.open(unzippedfile, 'r')
                    tar.extractall(untarred_folder)
                    tar.close()
                    os.remove(unzippedfile)
                    walkdir(untarred_folder)
                    # re-tar and re-zip
                    targzdirectory(untarred_folder, filepath)
                    shutil.rmtree(untarred_folder)
                else:
                    obfuscatefile(root, unzippedfile)
                    # re-zip
                    gzfile(unzippedfile)
                    os.remove(unzippedfile)
            else:
                obfuscatefile(root, filepath)


walkdir(logpath)