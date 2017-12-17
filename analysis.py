"""Learns quark/gluon discrimination using one of several scikit-learn models.
"""
from __future__ import division, print_function
import argparse
import sys
import os
import datetime
import pickle
import math
import webbrowser

from sklearn.externals import joblib
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.naive_bayes import GaussianNB
from sklearn.neural_network import MLPClassifier
from sklearn.metrics import classification_report
from sklearn.metrics import confusion_matrix
from sklearn.metrics import roc_curve, auc
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from dask_searchcv import RandomizedSearchCV
from dask.distributed import Client
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

import data
import constants

def print_classification_report(model, X, y, title):
  prediction = model.predict(X)
  print("Classification report on {}:".format(title))
  print()
  print(classification_report(y, prediction, target_names=['quark', 'gluon']))
  print()
  sns.set()
  mat = confusion_matrix(y, prediction)
  sns.heatmap(mat.T, square=True, annot=True, fmt='d', cbar=False)
  plt.xlabel('true label')
  plt.ylabel('predicted label')
  plt.title(title)

def print_hyperparameter_report(model):
  print("Best parameters on development set:")
  print()
  print(model.best_params_)
  print()
  print("Scores for each parameter combination on development set:")
  print()
  for mean, std, params in zip(model.cv_results_['mean_test_score'], model.cv_results_['std_test_score'], model.cv_results_['params']):
    print("{:0.3} (+/-{:0.03}) for {!r}".format(mean, 2 * std, params))
  print()

def plot_scores(scores, timestamp):
  for model_name in constants.MODEL_NAMES:
    plt.plot(scores.columns, scores.loc[model_name], label=model_name)
  plt.xscale('log')
  plt.xlabel('n')
  plt.ylabel('mean accuracy')
  plt.title('Model Accuracy')
  plt.legend()
  plt.savefig(os.path.join(timestamp, 'model_scores.png'), bbox_inches='tight')
  plt.show()

def fit(X, y, model_name, print_report):
  """Fit the specified model to the given data, returning the model and its score on the evaluation data. """
  if model_name == 'GBRT':
    classifier = GradientBoostingClassifier()
    param_grid = {'learning_rate': [0.01, 0.1], 'n_estimators': [10, 100, 1000], 'max_depth': [2, 3, 4], 'subsample': [0.1, 0.5, 1.0]}
    n_iter = 10
  elif model_name == 'NB':
    classifier = GaussianNB()
    param_grid = {}
    n_iter = 1
  elif model_name == 'NN':
    classifier = Pipeline([('scale', StandardScaler()), ('nn', MLPClassifier())])
    param_grid = {'nn__alpha': (10.0 ** -np.arange(1, 7)).tolist()}
    n_iter = 6
  model = RandomizedSearchCV(classifier, param_grid, n_iter=n_iter, cache_cv=False)
  X_dev, X_eval, y_dev, y_eval = train_test_split(X, y)
  model.fit(X_dev, y_dev)
  if print_report:
    print_classification_report(model, X_eval, y_eval)
    if model_name == 'GBRT' or model_name == 'NN':
      print_hyperparameter_report(model)
  return model, model.score(X_eval, y_eval)

def analyze(args):
  timestamp = '{:%Y%m%d%H%M%S}'.format(datetime.datetime.now())
  os.mkdir(timestamp)
  with open(os.path.join(timestamp, 'args.txt'), 'w+') as fh:
    fh.write(str(args))
  X_standard, y_standard = data.get_features_and_labels(modified=False, recalculate=args.recalculate, max_events=args.max_events)
  X_modified, y_modified = data.get_features_and_labels(modified=True, recalculate=args.recalculate)
  client = Client('localhost:8786')
  webbrowser.open('http://localhost:8787')
  if args.model:
    fit(X_standard, y_standard, args.model, args.print_report)
    joblib.dump(model, os.path.join(timestamp, args.model + '.pkl'))
  elif args.compare_models:
    scores = {}
    # max_events is every positive power of 10 no greater than args.max_events.
    for max_events in 10**np.arange(1, int(math.floor(1+math.log(args.max_events, 10)))):
      score_slice = {}
      for model_name in constants.MODEL_NAMES:
        model, eval_score = fit(X_standard[:max_events], y_standard[:max_events], model_name, args.print_report)
        real_score = model.score(X_modified, y_modified)
        score_slice[model_name] = (eval_score, real_score)
      scores[max_events] = score_slice
    scores = pd.DataFrame(scores)
    plot_scores(scores, timestamp)

def main():
  parser = argparse.ArgumentParser(description='Analyze quark/gluon separation using a particular machine learning model.')
  group = parser.add_mutually_exclusive_group(required=True)
  group.add_argument('-m', '--model', choices=constants.MODEL_NAMES, help='Type of machine learning model to use.')
  group.add_argument('--compare_models', action='store_true', help='Fit all models and compare their performance.')
  parser.add_argument('--recalculate', action='store_true', help='Recalculate features from root files, instead of using pickled features.')
  parser.add_argument('--print_report', action='store_true', help='Print a report detailing the performance of the model.')
  parser.add_argument('--max_events', default=0, type=int, help='The maximum number of standard quark/gluon events to use in training (max_events <= 0 indicates to use all of them)')
  args = parser.parse_args()
  analyze(args)
  
if __name__ == "__main__":
  main()
