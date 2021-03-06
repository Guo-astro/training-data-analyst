# Copyright 2017 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Example implementation of image model in TensorFlow 
that can be trained and deployed on Cloud ML Engine
"""

import argparse
import json
import os

import model

import tensorflow as tf
from tensorflow.examples.tutorials.mnist import input_data

def make_train_input_fn(mnist, hparams):
  def input_fn():
    features, labels = tf.train.shuffle_batch([tf.constant(mnist.train.images), tf.constant(mnist.train.labels)],
                                            batch_size=hparams['train_batch_size'], capacity=5000, min_after_dequeue=2000, enqueue_many=True)
    features = {'image': features}
    return features, labels
  return input_fn

def make_eval_input_fn(mnist):
  def input_fn():
    features, labels = tf.constant(mnist.test.images), tf.constant(mnist.test.labels)
    features = {'image': features}
    return features, labels
  return input_fn

def image_classifier(features, labels, mode, params):
  ylogits, nclasses = model.linear_model(features['image'])
  probabilities = tf.nn.softmax(ylogits)
  classes = tf.cast(tf.argmax(probabilities, 1), tf.uint8)
  if mode == tf.estimator.ModeKeys.TRAIN or mode == tf.estimator.ModeKeys.EVAL:
    loss = tf.reduce_mean(tf.nn.softmax_cross_entropy_with_logits(logits=ylogits, labels=tf.one_hot(labels, nclasses)))
    evalmetrics =  {'accuracy': tf.metrics.accuracy(classes, labels)}
    if mode == tf.estimator.ModeKeys.TRAIN:
      train_op = tf.contrib.layers.optimize_loss(loss, tf.train.get_global_step(),
                                                 learning_rate=params['learning_rate'], optimizer="Adam")
    else:
      train_op = None
  else:
    loss = None
    train_op = None
    evalmetrics = None
 
  return tf.estimator.EstimatorSpec(
        mode=mode,
        predictions={"probabilities": probabilities, "classes": classes},
        loss=loss,
        train_op=train_op,
        eval_metric_ops=evalmetrics,
        export_outputs={'classes': tf.estimator.export.PredictOutput({"probabilities": probabilities, "classes": classes})}
    )

def create_custom_estimator(output_dir, hparams):
  training_config = tf.contrib.learn.RunConfig(save_checkpoints_secs=None,
                                               save_checkpoints_steps=hparams['train_steps']/5)
  return tf.estimator.Estimator(model_fn=image_classifier, model_dir=output_dir, 
                                config=training_config, params=hparams)

def make_experiment_fn(output_dir, data_dir, hparams):
  def experiment_fn(output_dir):
    mnist = input_data.read_data_sets(data_dir, reshape=False)  
    return tf.contrib.learn.Experiment(
      estimator=create_custom_estimator(output_dir, hparams),
      train_input_fn=make_train_input_fn(mnist, hparams),
      eval_input_fn=make_eval_input_fn(mnist),
      train_steps=hparams['train_steps'],
      eval_steps=1,
      min_eval_frequency=min(100,hparams['train_steps']/10),
      export_strategies=tf.contrib.learn.utils.saved_model_export_utils.make_export_strategy(serving_input_fn=model.serving_input_fn)
    )
  return experiment_fn

if __name__ == '__main__':
  parser = argparse.ArgumentParser()
  # Input Arguments
  parser.add_argument(
      '--train_batch_size',
      help='Batch size for training steps',
      type=int,
      default=512
  )
  parser.add_argument(
      '--learning_rate',
      help='Initial learning rate for training',
      type=float,
      default=0.01
  )
  parser.add_argument(
      '--train_steps',
      help="""\
      Steps to run the training job for. If --num-epochs is not specified,
      this must be. Otherwise the training job will run indefinitely.\
      """,
      type=int
  )
  parser.add_argument(
      '--output_dir',
      help='GCS location to write checkpoints and export models',
      required=True
  )
  parser.add_argument(
      '--job-dir',
      help='this model ignores this field, but it is required by gcloud',
      default='junk'
  )

  args = parser.parse_args()
  hparams = args.__dict__
  
  # unused args provided by service
  hparams.pop('job_dir', None)
  hparams.pop('job-dir', None)

  output_dir = hparams.pop('output_dir')
  # Append trial_id to path for hptuning
  output_dir = os.path.join(
      output_dir,
      json.loads(
          os.environ.get('TF_CONFIG', '{}')
      ).get('task', {}).get('trail', '')
  )
  
  # Run the training job
  tf.contrib.learn.learn_runner.run(make_experiment_fn(output_dir, 'mnist/data', hparams), output_dir)

