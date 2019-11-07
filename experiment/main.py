"""
Modified from:  https://github.com/chengyangfu/pytorch-vgg-cifar10/blob/master/vgg.py
"""

import sys

from util.eval import accuracy_from_data_loader
from util.ourlogging import Logger

sys.path.append("../")
import argparse
import os
import shutil
import time

import torch
import torch.nn as nn
import torch.nn.parallel
import torch.backends.cudnn as cudnn
import torch.optim
import torch.utils.data
import torchvision.transforms as transforms
import torchvision.datasets as datasets
from model.network import vgg_2
from torchsummary import summary


def main():
    use_cpu = True
    batch_size = 128
    learn_rate = 0.01
    num_epochs = 300

    model = vgg_2.vgg19()
    logger = Logger(model)

    model.features = torch.nn.DataParallel(model.features)
    if use_cpu:
        model.cpu()
    else:
        model.cuda()

    print(summary(model, input_size=(3, 32, 32)))

    cudnn.benchmark = True

    '''
    normalize = transforms.Normalize(mean=[0.485, 0.456, 0.406],
                                     std=[0.229, 0.224, 0.225])
    '''

    normalize = transforms.Normalize((0.5, 0.5, 0.5), (0.5, 0.5, 0.5))
    train_loader = torch.utils.data.DataLoader(
        datasets.CIFAR10(root='../data/cifar10/', train=True, transform=transforms.Compose([
            transforms.RandomHorizontalFlip(),
            transforms.RandomCrop(32, 4),
            transforms.ToTensor(),
            normalize,
        ]), download=True),
        batch_size=batch_size, shuffle=True)  # , pin_memory=True)

    val_loader = torch.utils.data.DataLoader(
        datasets.CIFAR10(root='../data/cifar10/', train=False, transform=transforms.Compose([
            transforms.ToTensor(),
            normalize,
        ])),
        batch_size=batch_size, shuffle=False)  # , pin_memory=True)

    # define loss function (criterion) and opptimizer
    criterion = nn.CrossEntropyLoss()
    if use_cpu:
        criterion = criterion.cpu()
    else:
        criterion = criterion.cuda()

    '''
    optimizer = torch.optim.SGD(model.parameters(), args.lr,
                                momentum=args.momentum,
                                weight_decay=args.weight_decay)
    '''
    optimizer = torch.optim.Adam(model.parameters(), lr=learn_rate)

    for epoch in range(num_epochs):
        # adjust_learning_rate(optimizer, epoch)

        # train for one epoch
        train(train_loader, model, criterion, optimizer, epoch, use_cpu=use_cpu, logger=logger, val_loader=val_loader)


def train(train_loader, model, criterion, optimizer, epoch, use_cpu=False, logger=None, val_loader=None, verbose=False,
          save_freq=80):
    """
        Run one train epoch
    """

    # switch to train mode
    model.train()
    running_loss = 0.0
    num_batches = train_loader.__len__()
    loss_history = []
    max_val_acc = 0

    for i, (input, target) in enumerate(train_loader):
        if not use_cpu:
            input = input.cuda()
            target = target.cuda()

        # compute output
        output = model(input)
        loss = criterion(output, target)

        # compute gradient and do SGD step
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

        # print statistics
        running_loss += loss.item()

        if i == num_batches - 1:
            log_loss = running_loss / num_batches
            loss_history.append(log_loss)
            if logger is not None:
                if val_loader is None:
                    logger.update_loss(log_loss, epoch + 1)
                    logger.log('[%d, %5d] loss: %.3f' % (epoch + 1, i + 1, log_loss), console=verbose)
                else:
                    val_acc = accuracy_from_data_loader(model, val_loader)
                    if val_acc > max_val_acc:
                        max_val_acc = val_acc
                        if epoch >= 100:
                            logger.save_model(f'{epoch + 1}_best', best=True)
                    logger.log('[%d, %5d] loss: %.3f val_acc: %.3f' % (epoch + 1, i + 1, log_loss, val_acc),
                               console=verbose)
                logger.update_loss(log_loss, epoch + 1)
            running_loss = 0.0

    if epoch > 0 and epoch % save_freq == 0:
        logger.save_model(epoch + 1)


'''
def adjust_learning_rate(optimizer, epoch):
    """Sets the learning rate to the initial LR decayed by 2 every 30 epochs"""
    lr = args.lr * (0.5 ** (epoch // 30))
    for param_group in optimizer.param_groups:
        param_group['lr'] = lr
'''


if __name__ == '__main__':
    main()
