## 自动写诗的例子
import sys
sys.path.append("/Users/xingzhaohu/Downloads/code/python/ml/ml_code/bert/bert_seq2seq")
import torch 
from tqdm import tqdm
import torch.nn as nn 
from torch.optim import Adam
import pandas as pd
import numpy as np
import os
import json
import time
import bert_seq2seq
from torch.utils.data import Dataset, DataLoader
from bert_seq2seq.tokenizer import Tokenizer, load_chinese_base_vocab
from bert_seq2seq.utils import load_bert, load_model_params, load_recent_model
# 引入自定义数据集
from bert_seq2seq.bert_dataset import BertDataset

def read_corpus(dir_path, vocab_path):
    """
    读原始数据
    """
    sents_src = []
    sents_tgt = []
    in_path = dir_path + "/in.txt"
    out_path = dir_path + "/out.txt"
    with open(in_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
        for line in lines:
            sents_src.append(line.strip())
    with open(out_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
        for line in lines:
            sents_tgt.append(line.strip())

    return sents_src, sents_tgt
    
def collate_fn(batch):
    """
    动态padding， batch为一部分sample
    """

    def padding(indice, max_length, pad_idx=0):
        """
        pad 函数
        注意 token type id 右侧pad是添加1而不是0，1表示属于句子B
        """
        pad_indice = [item + [pad_idx] * max(0, max_length - len(item)) for item in indice]
        return torch.tensor(pad_indice)

    token_ids = [data["token_ids"] for data in batch]
    max_length = max([len(t) for t in token_ids])
    token_type_ids = [data["token_type_ids"] for data in batch]

    token_ids_padded = padding(token_ids, max_length)
    token_type_ids_padded = padding(token_type_ids, max_length)
    target_ids_padded = token_ids_padded[:, 1:].contiguous()

    return token_ids_padded, token_type_ids_padded, target_ids_padded

class Trainer:
    def __init__(self):
        # 加载数据
        data_dir = "./corpus/对联"
        self.vocab_path = "./state_dict/roberta_wwm_vocab.txt" # roberta模型字典的位置
        self.sents_src, self.sents_tgt = read_corpus(data_dir, self.vocab_path)
        self.model_name = "roberta" # 选择模型名字
        self.model_path = "./state_dict/roberta_wwm_pytorch_model.bin" # roberta模型位置
        self.recent_model_path = "" # 用于把已经训练好的模型继续训练
        self.model_save_path = "./bert_model.bin"
        self.batch_size = 16
        self.lr = 1e-5
        # 加载字典
        self.word2idx = load_chinese_base_vocab(self.vocab_path)
        # 判断是否有可用GPU
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        print("device: " + str(self.device))
        # 定义模型
        self.bert_model = load_bert(self.vocab_path, model_name=self.model_name)
        ## 加载预训练的模型参数～
        load_model_params(self.bert_model, self.model_path)
        # 将模型发送到计算设备(GPU或CPU)
        self.bert_model.to(self.device)
        # 声明需要优化的参数
        self.optim_parameters = list(self.bert_model.parameters())
        self.optimizer = torch.optim.Adam(self.optim_parameters, lr=self.lr, weight_decay=1e-3)
        # 声明自定义的数据加载器
        dataset = BertDataset(self.sents_src, self.sents_tgt, self.vocab_path)
        self.dataloader =  DataLoader(dataset, batch_size=self.batch_size, shuffle=True, collate_fn=collate_fn)

    def train(self, epoch):
        # 一个epoch的训练
        self.bert_model.train()
        self.iteration(epoch, dataloader=self.dataloader, train=True)
    
    def save(self, save_path):
        """
        保存模型
        """
        torch.save(self.bert_model.state_dict(), save_path)
        print("{} saved!".format(save_path))

    def iteration(self, epoch, dataloader, train=True):
        total_loss = 0
        start_time = time.time() ## 得到当前时间
        step = 0
        for token_ids, token_type_ids, target_ids in tqdm(dataloader,position=0, leave=True):
            step += 1
            if step % 5000 == 0:
                self.bert_model.eval()
                test_data = ["花海总涵功德水", "广汉飞霞诗似玉", "执政为民，德行天下"]
                for text in test_data:
                    print(self.bert_model.generate(text, beam_size=3,device=self.device))
                self.bert_model.train()

            token_ids = token_ids.to(self.device)
            token_type_ids = token_type_ids.to(self.device)
            target_ids = target_ids.to(self.device)
            # 因为传入了target标签，因此会计算loss并且返回
            predictions, loss = self.bert_model(token_ids,
                                                token_type_ids,
                                                labels=target_ids,
                                                device=self.device
                                                )
            # 反向传播
            if train:
                # 清空之前的梯度
                self.optimizer.zero_grad()
                # 反向传播, 获取新的梯度
                loss.backward()
                # 用获取的梯度更新模型参数
                self.optimizer.step()

            # 为计算当前epoch的平均loss
            total_loss += loss.item()
        
        end_time = time.time()
        spend_time = end_time - start_time
        # 打印训练信息
        print("epoch is " + str(epoch)+". loss is " + str(total_loss) + ". spend time is "+ str(spend_time))
        # 保存模型
        self.save(self.model_save_path)

if __name__ == '__main__':
    
    trainer = Trainer()
    train_epoches = 10
    for epoch in range(train_epoches):
        # 训练一个epoch
        trainer.train(epoch)
