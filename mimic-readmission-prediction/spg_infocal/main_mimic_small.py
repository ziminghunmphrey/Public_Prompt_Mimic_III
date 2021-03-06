# Copyright 2020 . All Rights Reserved.
# Author : Lei Sha
import functools
print = functools.partial(print, flush=True)
import argparse
import os
import pandas as pd

from textdataMimic import TextDataMimic
import time, sys
import torch
import torch.autograd as autograd
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from tqdm import tqdm
import time, datetime
import math, random
from datetime import date
import nltk
import pickle
from nltk.translate.bleu_score import corpus_bleu, SmoothingFunction
# import matplotlib.pyplot as plt
import numpy as np
import copy
from Hyperparameters import args
from LanguageModel_mimic import LanguageModel

from LSTM import LSTM_Model
from LSTM_att import LSTM_att_Model
from LSTM_IB import LSTM_IB_Model
import LSTM_IB_GAN_small
from LSTM_IB_complete import LSTM_IB_CP_Model
from Transformer import TransformerModel
from LSTM_capIB import LSTM_capsule_IB_Model
from LSTM_cap import LSTM_capsule_Model
from LSTM_iterIB import LSTM_iterIB_Model
from LSTM_grid import LSTM_grid_Model
# from LSTM_GMIB import LSTM_GMIB_Model
from LSTM_GMIB_mimic import LSTM_GMIB_Model


import LSTM_IB_GAN_mimic_small

parser = argparse.ArgumentParser()
parser.add_argument('--gpu', '-g')
parser.add_argument('--modelarch', '-m')
parser.add_argument('--choose', '-c')
parser.add_argument('--use_big_emb', '-be')
parser.add_argument('--use_new_emb', '-ne')
parser.add_argument('--date', '-d')
parser.add_argument('--model_dir', '-md')
parser.add_argument('--encarch', '-ea')
cmdargs = parser.parse_args()

usegpu = True

if cmdargs.gpu is None:
    usegpu = False
else:
    usegpu = True
    args['device'] = 'cuda:' + str(cmdargs.gpu)

if cmdargs.modelarch is None:
    args['model_arch'] = 'lstm'
else:
    args['model_arch'] = cmdargs.modelarch

if cmdargs.choose is None:
    args['choose'] = 0
else:
    args['choose'] = int(cmdargs.choose)

if cmdargs.use_big_emb:
    args['big_emb'] = True
else:
    args['big_emb'] = False

if cmdargs.use_new_emb:
    args['new_emb'] = True
    emb_file_path = "newemb200"
else:
    args['new_emb'] = False
    emb_file_path =  "orgembs"

if cmdargs.date is None:
    args['date'] = str(date.today())

if cmdargs.model_dir is None:
    # args['model_dir'] = "./artifacts/RCNN_IB_GAN_be_mimic3_org_embs2021-05-12.pt"
    args['model_dir'] = "./artifacts/RCNN_IB_GAN_be_mimic3_org_embs_LM2021-05-25.pt"
else:
    args["model_dir"] = str(cmdargs.model_dir)

if cmdargs.encarch is None:
    args['enc_arch'] = 'rcnn'
else:
    args['enc_arch'] = cmdargs.encarch

def asMinutes(s):
    m = math.floor(s / 60)
    s -= m * 60
    return '%dm %ds' % (m, s)


def timeSince(since, percent):
    now = time.time()
    s = now - since
    es = s / (percent)
    rs = es - s
    return '%s (%s)' % (asMinutes(s), datetime.datetime.now())


class Runner:
    def __init__(self):
        self.model_path =args['rootDir'] + '/LSTM_IB_GAN_mimic_'+ emb_file_path+'_small'+args['date']+'.mdl'

    def main(self):

        args['datasetsize'] = 'small'
        if args['model_arch'] in ['lstmgrid']:
            args['batchSize'] = 64
        elif args['model_arch'] in ['lstmibgan']:
            args['classify_type'] = 'single'
            args['batchSize'] = 128
        elif args['model_arch'] in ['lstmibgan_law']:
            args['classify_type'] = 'single'
            args['batchSize'] = 64
            args['task'] = 'law'
        elif args['model_arch'] in ['lstmibgan_toi']:
            args['classify_type'] = 'single'
            args['batchSize'] = 64
            args['task'] = 'toi'

        self.textData = TextDataMimic("mimic", "../clinicalBERT/data/", "discharge", trainLM=False, test_phase=False, big_emb = args['big_emb'], new_emb = args['new_emb'])
        self.start_token = self.textData.word2index['START_TOKEN']
        self.end_token = self.textData.word2index['END_TOKEN']
        args['vocabularySize'] = self.textData.getVocabularySize()

        if args['model_arch'] in ['lstmibgan_law']:
            args['chargenum'] = self.textData.getLawNum()
        elif args['model_arch'] in ['lstmibgan_toi']:
            args['chargenum'] = 11
        else:
            args['chargenum'] = 2

        print(self.textData.getVocabularySize())

        if args['model_arch'] == 'lstm':
            print('Using LSTM model.')
            self.model = LSTM_Model(self.textData.word2index, self.textData.index2word, self.textData.index2vector)
            self.train()
        elif args['model_arch'] == 'lstmatt':
            print('Using LSTM attention model.')
            self.model = LSTM_att_Model(self.textData.word2index, self.textData.index2word)
            self.train()
        elif args['model_arch'] == 'transformer':
            print('Using Transformer model.')
            self.model = TransformerModel(self.textData.word2index, self.textData.index2word)
            self.train()
        elif args['model_arch'] == 'lstmib':
            print('Using LSTM information bottleneck model.')
            self.model = LSTM_IB_Model(self.textData.word2index, self.textData.index2word, self.textData.index2vector)
            self.train()
        elif args['model_arch'].startswith('lstmibgan'):
            print('Using LSTM information bottleneck GAN model. Mimic ')
            LM = torch.load(args['rootDir']+'/LMmimic.pkl', map_location=args['device'])
            for param in LM.parameters():
                param.requires_grad = True

            LSTM_IB_GAN_mimic_small.train(self.textData, LM)
        elif args['model_arch'] == 'lstmibcp':
            print('Using LSTM information bottleneck model. -- complete words')
            self.model = LSTM_IB_CP_Model(self.textData.word2index, self.textData.index2word)
            self.train()
        elif args['model_arch'] == 'lstmcapib':
            print('Using LSTM capsule information bottleneck model.')
            self.model = LSTM_capsule_IB_Model(self.textData.word2index, self.textData.index2word)
            self.train()
        elif args['model_arch'] == 'lstmiterib':
            print('Using LSTM iteratively information bottleneck model.')
            self.model = LSTM_iterIB_Model(self.textData.word2index, self.textData.index2word)
            self.train()
        elif args['model_arch'] == 'lstmcap':
            print('Using LSTM capsule model.')
            self.model = LSTM_capsule_Model(self.textData.word2index, self.textData.index2word)
            self.train()
        elif args['model_arch'] == 'lstmgrid':
            print('Using LSTM grid model.')
            self.model = LSTM_grid_Model(self.textData.word2index, self.textData.index2word)
            self.train()
        elif args['model_arch'] == 'lstmgmib':
            print('Using LSTM Gaussian Mixture IB model.')
            self.model = LSTM_GMIB_Model(self.textData.word2index, self.textData.index2word)
            self.model = self.model.to(args['device'])
            self.train()

    def train(self, print_every=10000, plot_every=10, learning_rate=0.001):
        start = time.time()
        plot_losses = []
        print_loss_total = 0  # Reset every print_every
        plot_loss_total = 0  # Reset every plot_every
        print_littleloss_total = 0
        print(type(self.textData.word2index))

        optimizer = optim.Adam(self.model.parameters(), lr=learning_rate, eps=1e-3, amsgrad=True)

        iter = 1
        batches = self.textData.getBatches()
        n_iters = len(batches)
        print('niters ', n_iters)

        args['trainseq2seq'] = False

        max_accu = -1

        training_stats = {}

        # create empty lists for running metrics
        val_accuracy_history = []
        Loss_history = []
        EM_history = []
        Gloss_history = []
        Dloss_history = []
        F_macro_history = []
        F_micro_history = []
        MP_history = []
        MR_history = []

        # accuracy = self.test('test', max_accu)
        for epoch in range(args['numEpochs']):
            losses = []

            for batch in batches:
                optimizer.zero_grad()
                x = {}
                x['enc_input'] = autograd.Variable(torch.LongTensor(batch.encoderSeqs)).to(args['device'])
                x['enc_len'] = batch.encoder_lens
                x['labels'] = autograd.Variable(torch.LongTensor(batch.label)).to(args['device'])

                # print("x_env_input shape is: ", x['enc_input'].shape)
                # print("x_enc_len shape is: ", len(x['enc_len']))
                # print("x labels shape is : ", x['labels'].shape)
                # print("current X is : ", x)
                if args['model_arch'] not in ['lstmiterib', 'lstmgrid', 'lstmgmib']:
                    x['labels'] = x['labels']

                if args['model_arch'] in ['lstmgmib']:
                    loss, littleloss = self.model(x)  # batch seq_len outsize
                    print_littleloss_total += littleloss.data
                else:
                    loss = self.model(x)  # batch seq_len outsize

                # print("current loss is: ", loss)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), args['clip'])

                optimizer.step()

                print_loss_total += loss.data
                plot_loss_total += loss.data

                losses.append(loss.data)

                if iter % print_every == 0:
                    print_loss_avg = print_loss_total / print_every
                    print_loss_total = 0
                    print_littleloss_avg = print_littleloss_total / print_every
                    print_littleloss_total = 0

                    if args['model_arch'] in ['lstmgmib']:
                        print('%s (%d %d%%) %.4f ' % (timeSince(start, iter / (n_iters * args['numEpochs'])),
                                                      iter, iter / n_iters * 100, print_loss_avg), end='')
                        print(print_littleloss_avg)
                    else:
                        print('%s (%d %d%%) %.4f' % (timeSince(start, iter / (n_iters * args['numEpochs'])),
                                                     iter, iter / n_iters * 100, print_loss_avg))

                if iter % plot_every == 0:
                    plot_loss_avg = plot_loss_total / plot_every
                    plot_losses.append(plot_loss_avg)
                    plot_loss_total = 0

                iter += 1

            if args['model_arch'] in ['lstmiterib', 'lstmgrid', 'lstmgmib']:
                accuracy, EM, p, r, acc, F_macro, F_micro, S = self.test('dev', max_accu)
                if EM > max_accu or max_accu == -1:
                    print('accuracy = ', EM, '>= min_accuracy(', max_accu, '), saving model...')
                    torch.save(self.model, self.model_path)
                    max_accu = accuracy

                print('Epoch ', epoch, 'loss = ', sum(losses) / len(losses), 'Valid accuracy = ', accuracy, EM, p, r,
                      acc, F_macro, F_micro, S,
                      'max accuracy=', max_accu)

                Loss_history.append(sum(losses)/len(losses))
                val_accuracy_history.append(accuracy)
                EM_history.append(EM)
                MP_history.append(p)
                MR_history.append(r)
                F_macro_history.append(F_macro)
                F_micro_history.append(F_micro)




            else:
                accuracy = self.test('dev', max_accu)
                if accuracy > max_accu or max_accu == -1:
                    print('accuracy = ', accuracy, '>= min_accuracy(', max_accu, '), saving model...')
                    torch.save(self.model, self.model_path)
                    max_accu = accuracy

                print('Epoch ', epoch, 'loss = ', sum(losses) / len(losses), 'Valid accuracy = ', accuracy,
                      'max accuracy=', max_accu)
                Loss_history.append(sum(losses)/len(losses))
                val_accuracy_history.append(accuracy)

        print("finished all training and testing now - saving metrics")
        if args['model_arch'] in ['lstmiterib', 'lstmgrid', 'lstmgmib']:
            # save each epochs Gloss and Dloss
            training_stats['epoch'] = list(range(len(Loss_history)))
            training_stats['Loss'] = Loss_history
            training_stats['Val. Accuracy'] = val_accuracy_history
            training_stats['F_macro'] = F_macro_history
            training_stats['F_micro'] = F_micro_history
            training_stats['mean_precision'] = MP_history
            training_stats['mean_recall'] = MR_history


            # print(training_stats)
            # save training stats to file
            pd.DataFrame(training_stats).to_csv(
                args['rootDir'] + "/training_stats" + args['model_arch'] + args['date'] + ".csv", index=False)
        else:
            training_stats['epoch'] = list(range(len(Loss_history)))
            training_stats['Loss'] = Loss_history
            training_stats['Val. Accuracy'] = val_accuracy_history
            # save training stats to file
            pd.DataFrame(training_stats).to_csv(
                args['rootDir'] + "/training_stats" + args['model_arch'] + args['date'] + ".csv", index=False)

        # self.test()
        # showPlot(plot_losses)

    def test(self, datasetname, max_accuracy, eps=1e-20):
        # if not hasattr(self, 'testbatches'):
        #     self.testbatches = {}
        # if datasetname not in self.testbatches:
        # self.testbatches[datasetname] = self.textData.getBatches(datasetname)
        right = 0
        total = 0

        dset = []

        exact_match = 0
        p = 0.0
        r = 0.0
        acc = 0.0

        TP_c = np.zeros(args['chargenum'])
        FP_c = np.zeros(args['chargenum'])
        FN_c = np.zeros(args['chargenum'])
        TN_c = np.zeros(args['chargenum'])

        with torch.no_grad():
            pppt = False
            for batch in self.textData.getBatches(datasetname):
                x = {}
                x['enc_input'] = autograd.Variable(torch.LongTensor(batch.encoderSeqs)).to(args['device'])
                x['enc_len'] = batch.encoder_lens
                x['labels'] = autograd.Variable(torch.LongTensor(batch.label)).to(args['device'])

                if args['model_arch'] in ['lstmiterib', 'lstmgrid', 'lstmgmib']:
                    print("model arch was: " + args['model_arch'] + " so in fp test loop!")
                    answer = self.model.predict(x).cpu().numpy()
                    print("the returned answer is: ", answer)
                    # TODO investigate the below line - no idea what this +2 business is
                    y = F.one_hot(torch.LongTensor(batch.label), num_classes=args['chargenum'] + 2)
                    print("current y in testing is: ", )
                    y = y[:, :, :args['chargenum']]  # add content class
                    print("y after adding content class? :", y)
                    y, _ = torch.max(y, dim=1)
                    y = y.bool().numpy()
                    exact_match += ((answer == y).sum(axis = 1) == args['chargenum']).sum()
                    total += answer.shape[0]
                    tp_c = ((answer == True) & (answer == y)).sum(axis = 0) # c
                    fp_c = ((answer == True) & (y == False)).sum(axis = 0) # c
                    fn_c = ((answer == False) & (y == True)).sum(axis = 0) # c
                    tn_c = ((answer == False) & (y == False)).sum(axis = 0) # c
                    TP_c += tp_c
                    FP_c += fp_c
                    FN_c += fn_c
                    TN_c += tn_c
                    right = exact_match
                else:
                    output_probs, output_labels = self.model.predict(x)
                    if args['model_arch'] == 'lstmib' or args['model_arch'] == 'lstmibcp':
                        output_labels, sampled_words, wordsamplerate = output_labels
                        # print("output labels are: ", output_labels)
                        if not pppt:
                            pppt = True
                            for w, choice in zip(batch.encoderSeqs[0], sampled_words[0]):
                                if choice[1] == 1:
                                    print(self.textData.index2word[w], end='')
                            print('sample rate: ', wordsamplerate[0])
                    elif args['model_arch'] == 'lstmcapib':
                        output_labels, sampled_words, wordsamplerate = output_labels
                        if not pppt:
                            pppt = True
                            for w, choice in zip(batch.encoderSeqs[0], sampled_words[0, output_labels[0], :]):
                                if choice == 1:
                                    print(self.textData.index2word[w], end='')
                            print('sample rate: ', wordsamplerate[0])

                    print("output labels are: ", output_labels.cpu().numpy())
                    print("true labels are: ", torch.LongTensor(batch.label).cpu().numpy())
                    batch_correct = output_labels.cpu().numpy() == torch.LongTensor(batch.label).cpu().numpy()
                    right += sum(batch_correct)
                    total += x['enc_input'].size()[0]

                    for ind, c in enumerate(batch_correct):
                        if not c:
                            dset.append((batch.encoderSeqs[ind], batch.label[ind], output_labels[ind]))

        accuracy = right / total
        print("accuracy yo: ", accuracy)

        if accuracy > max_accuracy:
            with open(args['rootDir'] + '/error_case_' + args['model_arch'] + args['date'] + '.txt', 'w') as wh:
                for d in dset:
                    wh.write(''.join([self.textData.index2word[wid] for wid in d[0]]))
                    wh.write('\t')
                    # wh.write(self.textData.lawinfo['i2c'][int(d[1])])
                    wh.write('\t')
                    # wh.write(self.textData.lawinfo['i2c'][int(d[2])])
                    wh.write('\n')
            wh.close()
        if args['model_arch'] in ['lstmiterib', 'lstmgrid', 'lstmgmib']:
            P_c = TP_c / (TP_c + FP_c)
            R_c = TP_c / (TP_c + FN_c)
            F_c = 2 * P_c * R_c / (P_c + R_c)
            F_macro = np.nanmean(F_c)
            TP_micro = np.sum(TP_c)
            FP_micro = np.sum(FP_c)
            FN_micro = np.sum(FN_c)

            P_micro = TP_micro / (TP_micro + FP_micro)
            R_micro = TP_micro / (TP_micro + FN_micro)
            F_micro = 2 * P_micro * R_micro / (P_micro + R_micro)
            S = 100 * (F_macro + F_micro) / 2
            return accuracy, exact_match / total, p, r, acc, F_macro, F_micro, S
        else:
            return accuracy

    def indexesFromSentence(self, sentence):
        return [self.textData.word2index[word] if word in self.textData.word2index else self.textData.word2index['UNK']
                for word in sentence]

    def tensorFromSentence(self, sentence):
        indexes = self.indexesFromSentence(sentence)
        # indexes.append(self.textData.word2index['END_TOKEN'])
        return torch.tensor(indexes, dtype=torch.long, device=device).view(-1, 1)

    def evaluate(self, sentence, correctlabel, max_length=20):
        with torch.no_grad():
            input_tensor = self.tensorFromSentence(sentence)
            input_length = input_tensor.size()[0]
            # encoder_hidden = encoder.initHidden()

            # encoder_outputs = torch.zeros(max_length, encoder.hidden_size, device=device)

            x = {}
            # print(input_tensor)
            x['enc_input'] = torch.transpose(input_tensor, 0, 1)
            x['enc_len'] = [input_length]
            x['labels'] = [correctlabel]
            # print(x['enc_input'], x['enc_len'])
            # print(x['enc_input'].shape)
            decoded_words, label, _ = self.model.predict(x, True)

            return decoded_words, label

    def evaluateRandomly(self, n=10):
        for i in range(n):
            sample = random.choice(self.textData.datasets['train'])
            print('>', sample)
            output_words, label = self.evaluate(sample[2], sample[1])
            output_sentence = ' '.join(output_words[0])  # batch=1
            print('<', output_sentence, label)
            print('')


if __name__ == '__main__':
    r = Runner()
    r.main()