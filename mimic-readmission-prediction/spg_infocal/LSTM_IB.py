import torch
import torch.autograd as autograd
from torch.autograd import Variable
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.nn.parameter import Parameter

import numpy as np

import datetime


from Encoder import Encoder
from Decoder import Decoder
from Hyperparameters import args

class LSTM_IB_Model(nn.Module):
    """
    Implementation of a seq2seq model.
    Architecture:
        Encoder/decoder
        2 LTSM layers
    """

    def __init__(self, w2i, i2w, i2v):
        """
        Args:
            args: parameters of the model
            textData: the dataset object
        """
        super(LSTM_IB_Model, self).__init__()
        print("Model creation...")

        self.word2index = w2i
        self.index2word = i2w
        self.max_length = args['maxLengthDeco']

        self.NLLloss = torch.nn.NLLLoss(reduction = 'none')
        self.CEloss =  torch.nn.CrossEntropyLoss(reduction = 'none')

        #TODO change this to pretrained embedding?
        self.embedding = nn.Embedding(args['vocabularySize'], args['embeddingSize']).to(args['device'])
        # self.embedding = nn.Embedding.from_pretrained(torch.FloatTensor(i2v))
        # self.embedding.weight.requires_grad = False

        self.encoder = Encoder(w2i, i2w, self.embedding).to(args['device'])

        self.tanh = nn.Tanh()
        self.softmax = nn.Softmax(dim = -1)

        self.x_2_prob_z = nn.Sequential(
            nn.Linear(args['hiddenSize'], 2)
          ).to(args['device'])
        self.z_to_fea = nn.Linear(args['hiddenSize'], args['hiddenSize']).to(args['device'])

        self.ChargeClassifier = nn.Sequential(
            nn.Linear(args['hiddenSize'], args['chargenum']),
            nn.LogSoftmax(dim=-1)
          ).to(args['device'])
        
    def sample_gumbel(self, shape, eps=1e-20):
        U = torch.rand(shape).to(args['device'])
        return -torch.log(-torch.log(U + eps) + eps)

    def gumbel_softmax_sample(self, logits, temperature):
        y = logits + self.sample_gumbel(logits.size())
        return F.softmax(y / temperature, dim=-1)

    def gumbel_softmax(self, logits, temperature = args['temperature']):
        """
        ST-gumple-softmax
        input: [*, n_class]
        return: flatten --> [*, n_class] an one-hot vector
        """
        y = self.gumbel_softmax_sample(logits, temperature)
        shape = y.size()
        _, ind = y.max(dim=-1)
        y_hard = torch.zeros_like(y).view(-1, shape[-1])
        y_hard.scatter_(1, ind.view(-1, 1), 1)
        y_hard = y_hard.view(*shape)
        y_hard = (y_hard - y).detach() + y
        return y_hard

    def forward(self, x, eps = 0.000001):
        '''
        :param encoderInputs: [batch, enc_len]
        :param decoderInputs: [batch, dec_len]
        :param decoderTargets: [batch, dec_len]
        :return:
        '''

        # print(x['enc_input'])
        self.encoderInputs = x['enc_input'].to(args['device'])
        self.encoder_lengths = x['enc_len']
        self.classifyLabels = x['labels'].to(args['device'])
        self.batch_size = self.encoderInputs.size()[0]
        self.seqlen = self.encoderInputs.size()[1]

        mask = torch.sign(self.encoderInputs).float()

        en_outputs, en_state = self.encoder(self.encoderInputs, self.encoder_lengths)  # batch seq hid
        # print(en_outputs.size())
        z_logits = self.x_2_prob_z(en_outputs.to(args['device'])) # batch seq 2


        z_logits_fla = z_logits.reshape((self.batch_size * self.seqlen, 2))
        sampled_seq = self.gumbel_softmax(z_logits_fla).reshape((self.batch_size, self.seqlen, 2))  # batch seq  //0-1
        sampled_seq = sampled_seq * mask.unsqueeze(2)

        # print(sampled_seq)

        sampled_num = torch.sum(sampled_seq[:,:,1], dim = 1) # batch
        sampled_num = (sampled_num == 0).to(args['device'], dtype=torch.float32)  + sampled_num
        sampled_word = en_outputs * (sampled_seq[:,:,1].unsqueeze(2))  # batch seq hid
        # print(sampled_word[0,:,:])
        # exit()
        s_w_feature = self.z_to_fea(sampled_word)
        s_w_feature = torch.sum(s_w_feature, dim = 1)/ sampled_num.unsqueeze(1)# batch hid

        z_prob = self.softmax(z_logits)
        I_x_z = torch.mean(torch.sum(-torch.log(z_prob[:,:,0]+ eps), dim = 1))
        # print(I_x_z)
        # en_hidden, en_cell = en_state   #2 batch hid
        # print(z_prob[0,:,:], sampled_num, I_x_z, torch.sum(-torch.log(z_prob[0,:,0]+ eps)))

        output = self.ChargeClassifier(s_w_feature).to(args['device'])  # batch chargenum

        recon_loss = self.NLLloss(output, self.classifyLabels).to(args['device'])

        recon_loss_mean = torch.mean(recon_loss).to(args['device'])


        # wordnum = torch.sum(mask, dim = 1)
        # print(sampled_num / wordnum)
        # exit()

        return recon_loss_mean + I_x_z * 0.1

    def predict(self, x):
        encoderInputs = x['enc_input'].to(args['device'])
        encoder_lengths = x['enc_len']

        batch_size = encoderInputs.size()[0]
        seqlen = encoderInputs.size()[1]
        mask = torch.sign(encoderInputs).float()

        en_outputs, en_state = self.encoder(encoderInputs, encoder_lengths)

        z_logits = self.x_2_prob_z(en_outputs.to(args['device']))  # batch seq 2

        z_logits_fla = z_logits.reshape((batch_size * seqlen, 2))
        sampled_seq = self.gumbel_softmax(z_logits_fla).reshape((batch_size, seqlen, 2))  # batch seq  //0-1
        sampled_seq = sampled_seq * mask.unsqueeze(2)

        sampled_num = torch.sum(sampled_seq[:,:,1], dim = 1) # batch
        sampled_num = (sampled_num == 0).to(args['device'], dtype=torch.float32)  + sampled_num
        sampled_word = en_outputs * (sampled_seq[:, :, 1].unsqueeze(2))  # batch seq hid
        s_w_feature = self.z_to_fea(sampled_word)
        s_w_feature = torch.sum(s_w_feature, dim = 1)/ sampled_num.unsqueeze(1)# batch hid


        output = self.ChargeClassifier(s_w_feature).to(args['device'])  # batch chargenum

        wordnum = torch.sum(mask, dim = 1)

        return output,  (torch.argmax(output, dim = -1), sampled_seq, sampled_num/wordnum)
