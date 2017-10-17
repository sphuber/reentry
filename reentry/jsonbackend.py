# -*- coding: utf8 -*-
"""A backend that uses a json file to store entry points"""
import json

from reentry.abcbackend import BackendInterface


class JsonBackend(BackendInterface):
    """
    Backend using json
    """

    def __init__(self, datafile=None):
        super(JsonBackend, self).__init__()
        from os.path import join, dirname, exists
        self.datafile = join(dirname(__file__), 'js_data')
        self.datafile = datafile or self.datafile
        if not exists(self.datafile):
            with open(self.datafile, 'w') as datafp:
                datafp.write('{}')
        self.epmap = self.read()

    def read(self):
        """
        read state from storage
        """
        with open(self.datafile, 'r') as cache_file_obj:
            return json.load(cache_file_obj)

    def write(self):
        """
        write the current state to storage
        """
        with open(self.datafile, 'w') as cache_file_obj:
            json.dump(self.epmap, cache_file_obj)

    def write_pr_dist(self, dist):
        """
        add a distribution, empty by default
        """
        dname, epmap = self.pr_dist_map(dist)
        self.write_dist_map(dname, epmap)

    def write_dist_map(self, distname, entry_point_map=None):
        dname = distname
        # extract entry points that are clearly not for plugins
        entry_point_map.pop('console_scripts', None)
        entry_point_map.pop('gui_scripts', None)
        entry_point_map.pop('distutils.commands', None)
        entry_point_map.pop('distutils.setup_keywords', None)
        entry_point_map.pop('setuptools.installation', None)
        entry_point_map.pop('setuptools.file_finders', None)
        entry_point_map.pop('egg_info.writers', None)
        entry_point_map = {
            k: {kk: str(vv)
                for kk, vv in v.iteritems()}
            for k, v in entry_point_map.iteritems()
        }
        # update entry point storage
        # --> only if there is something to update though
        if entry_point_map:
            if not self.epmap.get(dname):
                self.epmap[dname] = {}
            self.epmap[dname].update(entry_point_map)
            self.write()

    def write_st_dist(self, dist):
        """
        add a distribution during it's install
        """
        dname = dist.get_name()
        epmap = dist.entry_points.copy()
        for group in epmap:
            elist = epmap[group]
            epmap[group] = {i.split(' = ', 1)[0]: i for i in elist}
        self.write_dist_map(dname, epmap)

    def iter_group(self, group):
        """
        iterate over entry points within a given group
        """
        from reentry.entrypoint import EntryPoint
        for dist in self.epmap:
            for _, entry_point_spec in self.epmap[dist].get(group,
                                                            {}).iteritems():
                yield EntryPoint.parse(entry_point_spec)

    def get_pr_dist_map(self, dist):
        return self.get_dist_map(dist.project_name)

    def get_dist_map(self, dist):
        """
        Return the entry map of a given distribution
        """
        from reentry.entrypoint import EntryPoint
        dmap = self.epmap.get(dist, {}).copy()
        for gname in dmap:
            for epname in dmap[gname]:
                dmap[gname][epname] = EntryPoint.parse(dmap[gname][epname])
        return dmap

    def get_ep(self, group, name, dist=None):
        """
        Get an entry point

        :param group: the group name
        :param name: the entry point name
        :param dist: if not given, search in all dists

        if no dist was given, and the search turned up more than one
        entry point with the same name, returns a list of entrypoints
        else, returns an entry point
        """
        from reentry.entrypoint import EntryPoint
        if not dist:
            specs = []
            for dist_name in self.epmap.keys():
                spc = self.get_ep(group, name, dist=dist_name)
                if spc:
                    specs.append(spc)
            if len(specs) > 1:
                return specs
            elif len(specs) == 1:
                return specs[0]
        else:
            distribution_map = self.epmap.get(dist, {})
            group_map = distribution_map.get(group, {})
            spec = group_map.get(name)
            if spec:
                return EntryPoint.parse(spec)

    def get_dist_names(self):
        """
        Returns a list of distribution names
        """
        return self.epmap.keys()

    def get_group_names(self):
        """
        Returns a list of group names
        """
        glist = []
        for dist in self.get_dist_names():
            glist.extend(self.epmap[dist].keys())

        return list(set(glist))

    def rm_dist(self, distname):
        """
        removes a distributions entry points from the storage
        """
        if distname in self.get_dist_names():
            self.epmap.pop(distname)
        self.write()

    def rm_group(self, group):
        """
        removes a group from all dists
        """
        for dist in self.epmap:
            self.epmap[dist].pop(group, None)
        self.write()

    def clear(self):
        """
        completely clear entry_point storage
        """
        self.epmap = {}
        self.write()

    def get_map(self, dist=None, group=None, name=None):
        """
        see BackendInterface docs
        """
        import re
        from reentry.entrypoint import EntryPoint
        # sanitize dist kwarg
        dist_list = _listify(dist)
        if dist_list is None:
            dist_list = self.get_dist_names()

        # sanitize groups kwarg
        group_list = _listify(group)
        if group_list is None:
            group_list = self.get_group_names()
        # sanitize name kwarg
        name = _listify(name)

        entry_point_map = {}
        for distribution in dist_list:
            for group_name in self._filter_groups_by_distribution(
                    distribution_list=[distribution], group_list=group_list):
                group_map = {}
                for ep_name, entry_point in self.epmap[distribution][
                        group_name].iteritems():
                    if not name or any([re.match(i, ep_name) for i in name]):
                        group_map[ep_name] = EntryPoint.parse(entry_point)
                if group_map:
                    if group_name not in entry_point_map:
                        entry_point_map[group_name] = {}
                    entry_point_map[group_name].update(group_map)
        return entry_point_map

    def _filter_groups_by_distribution(self,
                                       distribution_list,
                                       group_list=None):
        """List only groups (optionally from a given list of groups) registered for the given list of distributions"""
        if group_list is None:
            group_list = self.get_group_names()
        group_set = set()
        for distribution in distribution_list:
            if distribution not in self.epmap:
                raise ValueError(
                    "The {} distribution was not found.".format(distribution))
            else:
                group_set.update([
                    group_name
                    for group_name in self.epmap[distribution].keys()
                    if group_name in group_list
                ])
        return group_set


def _listify(sequence_or_name):
    """Wrap a single name in a list, leave sequences and None unchanged"""
    from collections import Sequence
    if sequence_or_name is None:
        return None
    elif not isinstance(sequence_or_name, Sequence) or isinstance(
            sequence_or_name, (str, unicode)):
        return [sequence_or_name]
    return sequence_or_name
