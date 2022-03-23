# -*- coding: utf-8 -*-
# The DiverseSelector library provides a set of tools to select molecule
# subset with maximum molecular diversity.
#
# Copyright (C) 2022 The QC-Devs Community
#
# This file is part of DiverseSelector.
#
# DiverseSelector is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 3
# of the License, or (at your option) any later version.
#
# DiverseSelector is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, see <http://www.gnu.org/licenses/>
#
# --

"""Dissimilarity based diversity subset selection."""

import random

from DiverseSelector.base import SelectionBase
from DiverseSelector.metric import pairwise_dist
import numpy as np

__all__ = [
    "DissimilaritySelection",
]


class DissimilaritySelection(SelectionBase):
    """Dissimilarity based diversity subset selection."""

    def __init__(self,
                 initialization="medoid",
                 metric="Tanimoto",
                 random_seed=42,
                 feature_type=None,
                 mol_file=None,
                 feature_file=None,
                 num_selected=None,
                 arr_dist=None,
                 **kwargs,
                 ):
        """Base class for dissimilarity based subset selection."""
        super().__init__(metric, random_seed, feature_type, mol_file, feature_file, num_selected)
        self.initialization = initialization
        self.arr_dist = arr_dist

        # super(DissimilaritySelection, self).__init__(**kwargs)
        self.__dict__.update(kwargs)

        # the initial compound index
        self.arr_dist, self.starting_idx = self.pick_initial_compounds()

    def pick_initial_compounds(self):
        """Pick the initial compounds."""
        # todo: current version only works for molecular descriptors
        # pair-wise distance matrix
        if self.arr_dist is None:
            arr_dist_init = pairwise_dist(feature=self.features_norm,
                                          metric="euclidean")

        # use the molecule with maximum distance to initial medoid as  the starting molecule
        if self.initialization.lower() == "medoid":
            # https://www.sciencedirect.com/science/article/abs/pii/S1093326399000145?via%3Dihub
            # J. Mol. Graphics Mod., 1998, Vol. 16,
            # DISSIM: A program for the analysis of chemical diversity
            medoid_idx = np.argmin(self.arr_dist.sum(axis=0))
            # selected molecule with maximum distance to medoid
            starting_idx = np.argmax(self.arr_dist[medoid_idx, :])
            arr_dist_init = self.arr_dist

        elif self.initialization.lower() == "random":
            rng = np.random.default_rng(self.random_seed)
            starting_idx = rng.choice(np.arange(self.features_norm.shape[0]), 1)
            arr_dist_init = self.arr_dist

        return arr_dist_init, starting_idx

    def compute_diversity(self):
        """Compute the distance metrics."""
        # for iterative selection and final subset both
        pass
    
    def select(dissimilarity_function):
        def wrapper(*args, **kwargs):
            dissimilarity_function(*args, **kwargs)
        return wrapper

    @select
    def brutestrength(self, selected=None, n_selected=10, method='maxmin'):
        """Select the subset molecules with optimal diversity.

        Algorithm is adapted from https://doi.org/10.1016/S1093-3263(98)80008-9
        """

        if selected is None:
            selected = [self.starting_idx]
            return self.brutestrength(selected, n_selected, method)

        # if we all selected all n_selected molecules then return list of selected mols
        if len(selected) == n_selected:
            return selected

        if method == 'maxmin':
            # calculate min distances from each mol to the selected mols
            min_distances = np.min(self.arr_dist[selected], axis=0)

            # find molecules distance minimal distance of which is the maximum among all
            new_id = np.argmax(min_distances)

            # add selected molecule to the selected list
            selected.append(new_id)

            # call method again with an updated list of selected molecules
            return self.brutestrength(selected, n_selected, method)
        elif method == 'maxsum':
            sum_distances = np.sum(self.arr_dist[selected], axis=0)
            while True:
                new_id = np.argmax(sum_distances)
                if new_id in selected:
                    sum_distances[new_id] = 0
                else:
                    break
            selected.append(new_id)
            return self.brutestrength(selected, n_selected, method)
        else:
            raise ValueError(f"Method {method} not supported, choose maxmin or maxsum.")

    @select
    def sphereexclusion(self, selected=None, n_selected=10, s_max=1, order=None):
        if selected is None:
            selected = []
            return self.sphereexclusion(selected, n_selected, s_max, order)
        
        if order is None:        
            ref = [self.starting_idx]
            candidates = np.delete(np.arange(0, len(self.features_norm)), ref)
            distances = []
            for idx in candidates:
                ref_point = self.features_norm[ref[0]]
                data_point = self.features_norm[idx]
                distance_sq = 0
                for i in range(len(ref_point)):
                    distance_sq += (ref_point[i] - data_point[i]) ** 2
                distances.append((distance_sq, idx))
            distances.sort()
            order = [idx for dist, idx in distances]        
            return self.sphereexclusion(selected, n_selected, s_max, order)            

        for idx in order:
            if len(selected) == 0:
                selected.append(idx)
                continue        
            distances = []
            for selected_idx in selected:
                data_point = self.features_norm[idx]
                selected_point = self.features_norm[selected_idx]
                distance_sq = 0
                for i in range(len(data_point)):
                    distance_sq += (selected_point[i] - data_point[i]) ** 2
                distances.append(np.sqrt(distance_sq))
            min_dist = min(distances)
            if min_dist > s_max:
                selected.append(idx)
            if len(selected) == n_selected:
                return selected

        return selected

    @select
    def optisim(self, selected=None, n_selected=10, k=3, radius=2, recycling=None):
        if selected is None:
            selected = [self.starting_idx]
            return self.optisim(selected, n_selected, k, radius, recycling)

        if len(selected) >= n_selected:
            return selected

        if recycling is None:
            recycling = []

        candidates = np.delete(np.arange(0, len(self.features_norm)), selected + recycling)
        subsample = {}
        while len(subsample) < k:
            if len(candidates) == 0:
                if len(subsample) > 0:
                    selected.append(max(zip(subsample.values(), subsample.keys()))[1])
                    return self.optisim(selected, n_selected, k, radius, recycling)
                return selected
            index_new = candidates[np.random.randint(0, len(candidates))]
            distances = []
            for selected_idx in selected:
                data_point = self.features_norm[index_new]
                selected_point = self.features_norm[selected_idx]
                distance_sq = 0
                for i in range(len(data_point)):
                    distance_sq += (selected_point[i] - data_point[i]) ** 2
                distances.append(np.sqrt(distance_sq))
            min_dist = min(distances)
            if min_dist > radius:
                subsample[index_new] = min_dist
            else:
                recycling.append(index_new)
            candidates = np.delete(np.arange(0, len(self.features_norm)), selected + recycling + list(subsample.keys()))
        selected.append(max(zip(subsample.values(), subsample.keys()))[1])

        return self.optisim(selected, n_selected, k, radius, recycling)
