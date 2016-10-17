##############################################################
#
# Package  : AlphaPy
# Module   : data
# Version  : 1.0
# Copyright: Mark Conway
# Date     : July 29, 2015
#
##############################################################


#
# Imports
#

from datetime import datetime
from datetime import timedelta
from enum import Enum, unique
from frame import Frame
from frame import frame_name
from frame import read_frame
from globs import FEEDS
from globs import PSEP
from globs import SSEP
from globs import WILDCARD
from imblearn.combine import SMOTEENN
from imblearn.combine import SMOTETomek
from imblearn.ensemble import BalanceCascade
from imblearn.ensemble import EasyEnsemble
from imblearn.over_sampling import RandomOverSampler
from imblearn.over_sampling import SMOTE
from imblearn.under_sampling import ClusterCentroids
from imblearn.under_sampling import CondensedNearestNeighbour
from imblearn.under_sampling import EditedNearestNeighbours
from imblearn.under_sampling import InstanceHardnessThreshold
from imblearn.under_sampling import NearMiss
from imblearn.under_sampling import NeighbourhoodCleaningRule
from imblearn.under_sampling import OneSidedSelection
from imblearn.under_sampling import RandomUnderSampler
from imblearn.under_sampling import RepeatedEditedNearestNeighbours
from imblearn.under_sampling import TomekLinks
import logging
import numpy as np
import pandas as pd
import pandas_datareader.data as web
from scipy import sparse
from sklearn.preprocessing import LabelEncoder


#
# Initialize logger
#

logger = logging.getLogger(__name__)


#
# Sampling Methods
#

@unique
class SamplingMethod(Enum):
    under_random = 1
    under_tomek = 2
    under_cluster = 3
    under_nearmiss = 4
    under_ncr = 5
    over_random = 6
    over_smote = 7
    over_smoteb = 8
    over_smotesv = 9
    overunder_smote_tomek = 10
    overunder_smote_enn = 11
    ensemble_easy = 12
    ensemble_bc = 13


#
# Function get_data
#

def get_data(model, partition):
    """
    Read in data from the given directory in a given format.
    """

    logger.info("Loading Data")

    # Extract the model data

    base_dir = model.specs['base_dir']
    extension = model.specs['extension']
    features = model.specs['features']
    project = model.specs['project']
    separator = model.specs['separator']
    target = model.specs['target']
    test_file = model.specs['test_file']
    test_labels = model.specs['test_labels']
    train_file = model.specs['train_file']

    # Determine which partition to read

    if partition == 'train':
        filename = train_file
        test_labels = True
    elif partition == 'test':
        filename = test_file
    else:
        raise Exception("Partition %s not found", partition)

    # Read in the file

    directory = SSEP.join([base_dir, project, 'input'])
    df = read_frame(directory, filename, extension, separator)

    # Assign target and drop it if necessary

    if target in df.columns:
        logger.info("Found target %s in data frame", target)
        y = df[target]
        # transform with label encoder
        y = LabelEncoder().fit_transform(y)
        # drop the target as it has already been extracted into y
        logger.info("Dropping target %s from data frame", target)
        df = df.drop([target], axis=1)
    elif test_labels:
        logger.info("Target ", target, " not found")
        raise Exception("Target not found")

    # Extract features

    if features == WILDCARD:
        X = df
    else:
        X = df[features]

    # Labels are returned usually only for training data

    if test_labels:
        return X, y
    else:
        return X, None


#
# Function shuffle_data
#

def shuffle_data(model):
    """
    Shuffle training data
    """

    # Extract model parameters.

    seed = model.specs['seed']
    shuffle = model.specs['shuffle']

    # Extract model data.

    X_train = model.X_train
    y_train = model.y_train

    # Shuffle data

    if shuffle:
        logger.info("Shuffling Training Data")
        np.random.seed(seed)
        new_indices = np.random.permutation(y_train.size)
        model.X_train = X_train[new_indices]
        model.y_train = y_train[new_indices]
    else:
        logger.info("Skipping Shuffling")

    return model


#
# Function sample_data
#

def sample_data(model):
    """
    For imbalanced classes, try oversampling or undersampling.
    """

    logger.info("Sampling Data")

    # Extract model parameters.

    sampling_method = model.specs['sampling_method']
    sampling_ratio = model.specs['sampling_ratio']
    target = model.specs['target']
    target_value = model.specs['target_value']

    # Extract model data.

    X_train = model.X_train
    y_train = model.y_train

    # Calculate the sampling ratio if one is not provided.

    if sampling_ratio > 0.0:
        ratio = sampling_ratio
    else:
        uv, uc = np.unique(y_train, return_counts=True)
        ratio = (uc[not target_value] / uc[target_value]) - 1.0
    logger.info("Sampling Ratio for target %s [%r]: %f",
                target, target_value, ratio)

    # Choose the sampling method.

    if sampling_method == SamplingMethod.under_random:
        sampler = RandomUnderSampler()
    elif sampling_method == SamplingMethod.under_tomek:
        sampler = TomekLinks()
    elif sampling_method == SamplingMethod.under_cluster:
        sampler = ClusterCentroids()
    elif sampling_method == SamplingMethod.under_nearmiss:
        sampler = NearMiss(version=1)
    elif sampling_method == SamplingMethod.under_ncr:
        sampler = NeighbourhoodCleaningRule(size_ngh=51)
    elif sampling_method == SamplingMethod.over_random:
        sampler = RandomOverSampler(ratio=ratio)
    elif sampling_method == SamplingMethod.over_smote:
        sampler = SMOTE(ratio=ratio, kind='regular')
    elif sampling_method == SamplingMethod.over_smoteb:
        sampler = SMOTE(ratio=ratio, kind='borderline1')
    elif sampling_method == SamplingMethod.over_smotesv:
        sampler = SMOTE(ratio=ratio, kind='svm')
    elif sampling_method == SamplingMethod.overunder_smote_tomek:
        sampler = SMOTETomek(ratio=ratio)
    elif sampling_method == SamplingMethod.overunder_smote_enn:
        sampler = SMOTEENN(ratio=ratio)
    elif sampling_method == SamplingMethod.ensemble_easy:
        sampler = EasyEnsemble()
    elif sampling_method == SamplingMethod.ensemble_bc:
        sampler = BalanceCascade()
    else:
        raise ValueError("Unknown Sampling Method %s", sampling_method)

    # Get the newly sampled features.

    X, y = sampler.fit_sample(X_train, y_train)

    logger.info("Original Samples : %d", X_train.shape[0])
    logger.info("New Samples      : %d", X.shape[0])

    # Store the new features in the model.

    model.X_train = X
    model.y_train = y

    return model


#
# Function get_remote_data
#

def get_remote_data(group,
                    start = datetime.now() - timedelta(365),
                    end = datetime.now(),
                    dtcol = 'date'):
    gam = group.members
    feed = FEEDS[group.space.subject]
    for item in gam:
        logger.info("Getting %s data from %s to %s", item, start, end)
        df = web.DataReader(item, feed, start, end)
        if df is not None:
            df.reset_index(level=0, inplace=True)
            df = df.rename(columns = lambda x: x.lower().replace(' ',''))
            # time series, so date is the index
            df['date'] = pd.to_datetime(df['date'])
            df.index = df['date']
            del df['date']
            # allocate global Frame
            newf = Frame(item.lower(), group.space, df)
            if newf is None:
                logger.error("Could not allocate Frame for: %s", item)
        else:
            logger.info("Could not get data for: %s", item)
