from __future__ import division

import os
import random
import pdb # pylint: disable=unused-import
import functools

import numpy as np
import tensorflow as tf
import tensorflow.contrib.slim as slim # pylint: disable=E0611

def linear(input_, output_size, stddev=0.02, bias_start=0.0, activation_fn=None, name='linear'):
    shape = input_.get_shape().as_list()

    with tf.variable_scope(name):
        w = tf.get_variable('Matrix', [shape[1], output_size], tf.float32,
                            initializer=tf.random_normal_initializer(stddev=stddev))
        b = tf.get_variable('bias', [output_size],
                            initializer=tf.constant_initializer(bias_start))

        out = tf.nn.bias_add(tf.matmul(input_, w), b)

        if activation_fn != None:
            return activation_fn(out), w, b
        return out, w, b

class Qnetwork():
    # pylint: disable=too-many-instance-attributes
    def __init__(self, h_size, action_space, name):
        self.w = {}
        self.t_w = {}
        # self.scalarInput = tf.placeholder(shape=[None, 84 * 84 * 1], dtype=tf.float32)
        self.imageIn = tf.placeholder('float32', [None, 84, 84, 4], name="imageIn")
        self.conv1 = slim.conv2d(self.imageIn, 32, 8, 4, 'VALID',
                                 biases_initializer=None, scope='%s/conv1' % name)
        self.conv2 = slim.conv2d(self.conv1, 64, 4, 2, 'VALID',
                                 biases_initializer=None, scope='%s/conv2' % name)
        self.conv3 = slim.conv2d(self.conv2, 64, 3, 1, 'VALID',
                                 biases_initializer=None, scope='%s/conv3' % name)

        shape = self.conv3.get_shape().as_list()
        self.conv3_flat = tf.reshape(self.conv3,
                                     [-1, functools.reduce(lambda x, y: x * y, shape[1:])])

        self.value_hid, self.w['l4_val_w'], self.w['l4_val_b'] = \
            linear(self.conv3_flat, 512, activation_fn=tf.nn.relu, name=name + 'value_hid')

        self.adv_hid, self.w['l4_adv_w'], self.w['l4_adv_b'] = \
            linear(self.conv3_flat, 512, activation_fn=tf.nn.relu, name=name + 'adv_hid')

        self.Value, self.w['val_w_out'], self.w['val_w_b'] = \
          linear(self.value_hid, 1, name=name + 'value_out')

        self.Advantage, self.w['adv_w_out'], self.w['adv_w_b'] = \
          linear(self.adv_hid, action_space, name=name + 'adv_out')

        #  self.conv4 = slim.conv2d(self.conv3, 64, 5, 2, 'VALID',
        #                           biases_initializer=None, scope="conv4")
        #  self.fc = slim.fully_connected(self.conv4, h_size, activation_fn=tf.tanh)
        # Dueling network
        #  self.streamAC, self.streamVC = tf.split(self.conv4, 2, 3)
        #  pdb.set_trace()
        #  self.streamAC, self.streamVC = tf.split(self.fc, 2, 3)
        #  self.streamA = slim.flatten(self.streamAC)
        #  self.streamV = slim.flatten(self.streamVC)
        #  xavier_init = tf.contrib.layers.xavier_initializer()
        #  self.AW = tf.Variable(xavier_init([h_size//2, action_space]))
        #  self.AW = tf.Variable(xavier_init([h_size//2, 1]))
        #  self.VW = tf.Variable(xavier_init([h_size//2, 1]))
        #  self.Advantage = tf.matmul(self.streamA, self.AW)
        #  self.Value = tf.matmul(self.streamV, self.AW)
        # ?
        self.Qout = self.Value + tf.subtract(
            self.Advantage, tf.reduce_mean(self.Advantage, axis=1, keep_dims=True))
        self.predict = tf.argmax(self.Qout, 1)

        # optimizer
        self.targetQ = tf.placeholder(shape=[None], dtype=tf.float32)
        self.actions = tf.placeholder(shape=[None], dtype=tf.int32)
        self.actions_onehot = tf.one_hot(self.actions, action_space, dtype=tf.float32)

        self.Q = tf.reduce_sum(tf.multiply(self.Qout, self.actions_onehot), axis=1)

        self.td_error = tf.square(self.targetQ - self.Q)
        self.loss = tf.reduce_mean(self.td_error)
        self.trainer = tf.train.AdamOptimizer(learning_rate=0.0001)
        self.updateModel = self.trainer.minimize(self.loss)

class experience_buffer():
    def __init__(self, buffer_size=50000):
        self.buffer = []
        self.buffer_size = buffer_size

    def add(self, experience):
        if len(self.buffer) + len(experience) >= self.buffer_size:
            self.buffer[0:(len(experience) + len(self.buffer)) -  self.buffer_size] = []
        self.buffer.extend(experience)

    def getState(self, index):
        index = random.randint(4, self.buffer_size)
        samples = self.buffer[(index - 4):index]
        return np.reshape(np.array([ np.reshape(x.tolist(), (84, 84)) for x in np.array(samples)[:, 0] ]), (84, 84, 4))

    def sample(self, size):
        results = []
        for i in range(size):
            index = random.randint(4, self.buffer_size)
            sample = self.buffer[index] 
            preStates = self.getState(index - 1)
            postStates = self.getState(index)
            results.append([preStates, sample[1], sample[2], postStates, sample[4]])
        results = np.array(results)
        return results

class DoubleDuelingDQNAgent(object):
    def __init__(self, env, sess, FLAGS):

        self.env = env
        self.action_space = env.action_space

        self.config = {
            #  "batch_size": 16,
            "batch_size": 32,
            #  "batch_size": 8,
            "update_freq": 4,
            "y": .99,
            "startE": 1,
            "endE": 0.1,
            "total_steps": 5000000,
            "annealing_steps": 10000,
            "num_episodes": 10000,
            "pre_train_steps": 10000,
            "max_epLength": 1000,
            "screen_width": 84,
            "screen_height": 84,
            "load_model": False,
            "path": "./dqn",
            "h_size": 512,
            #  "h_size": 1024,
            "tau": 0.001,
        }

        #  tf.reset_default_graph()

        self.mainQN = Qnetwork(self.config["h_size"], env.action_space.n, 'main')
        self.targetQN = Qnetwork(self.config["h_size"], env.action_space.n, 'target')

        init = tf.global_variables_initializer()

        self.saver = tf.train.Saver()
        self.trainables = tf.trainable_variables()
        self.targetOps = self.updateTargetGraph(self.trainables, self.config["tau"])

        self.sess = sess
        self.sess.run(init)
        if self.config["load_model"]:
            print('Loading Model...')
            ckpt = tf.train.get_checkpoint_state(self.config["path"])
            self.saver.restore(sess, ckpt.model_checkpoint_path) # pylint: disable=E1101

        self.e = self.config["startE"]
        self.stepDrop = (self.config["startE"] - self.config["endE"]) \
            / self.config["annealing_steps"]

        self.jList = []
        self.rList = []
        self.total_steps = 0
        self.loss = 0

        if not os.path.exists(self.config["path"]):
            os.makedirs(self.config["path"])

        self.merged = tf.summary.merge_all()

        log_path = "%s/%s/%s/%s" % (FLAGS.log_dir,
                                    FLAGS.env_name,
                                    str(self.__class__.__name__),
                                    FLAGS.timestamp)
        self.writer = tf.summary.FileWriter("%s/%s" % (log_path, '/train'), sess.graph)

    def learn(self, state, action, reward, done, episodeBuffer, myBuffer):
        s1 = self.processState(state)
        self.total_steps += 1
        episodeBuffer.add(np.reshape(np.array([state, action, reward, s1, done]), [1, 5]))

        if self.total_steps > self.config["pre_train_steps"]:
            if self.e > self.config["endE"]:
                self.e -= self.stepDrop

            if self.total_steps % (self.config["update_freq"]) == 0:
                trainBatch = myBuffer.sample(self.config["batch_size"])
                self.lastStates = np.stack(trainBatch[:, 3])
                Q1 = self.sess.run(self.mainQN.predict, feed_dict={
                    self.mainQN.imageIn:np.stack(trainBatch[:, 3])
                })
                Q2 = self.sess.run(self.targetQN.Qout, feed_dict={
                    self.targetQN.imageIn:np.stack(trainBatch[:, 3])
                })
                end_multiplier = -(trainBatch[:, 4] - 1)
                doubleQ = Q2[range(self.config["batch_size"]), Q1]
                targetQ = trainBatch[:, 2] + (self.config["y"] * doubleQ * end_multiplier)
                _, loss = self.sess.run(
                    [self.mainQN.updateModel, self.mainQN.loss],
                    feed_dict={
                        self.mainQN.imageIn:np.stack(trainBatch[:, 0]),
                        self.mainQN.targetQ:targetQ,
                        self.mainQN.actions:trainBatch[:, 1]
                    })
                self.loss = loss
                self.updateTarget(self.targetOps, self.sess)
                #  self.train_writer.add_summary(summary, self.total_steps)
        return s1, self.loss, self.e

    def act(self, obs, reward, done):
        if np.random.rand(1) < self.e or self.total_steps < self.config["pre_train_steps"]:
            a = np.random.randint(0, 4)
        else:
            a = self.sess.run(self.mainQN.predict, feed_dict={self.mainQN.imageIn:self.lastStates})[0]
        return a

    def processState(self, states):
        return np.reshape(states, [states.size])

    def updateTargetGraph(self, tfVars, tau):
        total_vars = len(tfVars)
        op_holder = []
        for idx, var in enumerate(tfVars[0:total_vars//2]):
            op_holder.append(
                tfVars[idx + total_vars//2].assign(
                    (var.value() * tau) + ((1 - tau) * tfVars[idx + total_vars//2].value())))
        return op_holder

    def updateTarget(self, op_holder, sess):
        for op in op_holder:
            sess.run(op)
