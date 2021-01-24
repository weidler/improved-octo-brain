"""A script for all main experiments that allows running multiple experiments of the same strategy."""

import json

import torch
import torchvision
from torch import nn
from torch.utils.data import Subset, random_split, DataLoader
from torchvision import transforms

from evaluate import evaluate_on, load_test_set
from networks.util import build_network, AVAILABLE_NETWORKS, prepare_lc_builder
from utilities.data import get_number_of_classes, get_training_dataset
from utilities.eval import accuracy
from utilities.log import ExperimentLogger
from utilities.train import train_model

torch.backends.cudnn.deterministic = True
torch.backends.cudnn.benchmark = False

with open('default_config.json') as f:
    CONFIG = json.load(f).get('CONFIG', {})


def get_hp_params(args):
    if args.hpopt:
        with open('hp_params.json') as hp:
            conf = json.load(hp).get(args.hpopt)

        CONFIG[args.strategy][args.optim]['widths'] = conf['widths']
        CONFIG[args.strategy][args.optim]['damps'] = conf['damps']


def get_config(args):
    # check for HP optimization
    get_hp_params(args)

    # optionally overwrite config
    if args.widths:
        widths = [int(x) for x in args.widths.split(',')]
        assert len(widths) == args.coverage, \
            f"number of widths ({len(widths)}) does not match coverage {args.coverage}"
        CONFIG[args.strategy][args.optim]['widths'] = widths
    if args.damps:
        damps = [float(x) for x in args.damps.split(',')]
        assert len(damps) == args.coverage, \
            f"number of damps ({len(damps)}) does not match coverage {args.coverage}"
        CONFIG[args.strategy][args.optim]['damps'] = damps
    else:
        assert args.coverage == len(CONFIG[args.strategy][args.optim]['widths']) == len(
            CONFIG[args.strategy][args.optim]['damps']), \
            f"coverage ({args.coverage}) does not match configuration. Please check coverage param " \
            f"and change or overwrite config with arguments -s, -w, -d."

    return CONFIG


def get_params(args, param):
    assert param in ['widths', 'damps'], f"invalid param {param}"
    parameter = CONFIG[args.strategy][args.optim][param]

    return parameter


def run(args):
    # (de-)activate GPU utilization
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    if args.force_device is not None and args.force_device != "":
        if args.force_device in ["gpu", "cuda"]:
            args.force_device = "cuda"
        device = torch.device(args.force_device)
    print(f"Optimizing on device '{device}'")

    # load data
    train_data = get_training_dataset(args.data, force_crop=(24, 24) if args.network == "aA" else None)

    for i in range(0, args.i):
        train_set, validation_set = random_split(train_data, [int(len(train_data) * 0.9),
                                                              len(train_data) - int(len(train_data) * 0.9)])

        train_set_loader = DataLoader(train_set, batch_size=128, shuffle=True, num_workers=2, )
        validation_set_loader = DataLoader(validation_set, batch_size=128, shuffle=True, num_workers=2)
        image_channels, image_width, image_height = next(iter(train_set_loader))[0].shape[1:]
        n_classes = get_number_of_classes(train_data)

        lc_layer_function = prepare_lc_builder(args.strategy, args.widths, args.damps)
        network = build_network(args.network, input_shape=(image_channels, image_height, image_width),
                                n_classes=n_classes, lc=lc_layer_function, init_std=args.init_std)
        network.to(device)
        logger = ExperimentLogger(network, train_data)

        print(f"Model of type '{network.__class__.__name__}'{f' with lateral connections' if network.is_lateral else ''} "
              f"created with id {logger.id} in group {args.group}."
              f"\n\nStarting Training on {train_data.__class__.__name__} with {len(train_set)} samples distributed over {len(train_set_loader)} batches."
              f"\nOptimizing for {args.epochs} epochs and validating on {len(validation_set)} samples every epoch.")

        train_model(model=network,
                    train_set_loader=train_set_loader,
                    val_set_loader=validation_set_loader,
                    n_epochs=args.epochs,
                    logger=logger,
                    device=device)

        test_data = load_test_set(image_channels, image_height, image_width, args.data)
        evaluate_on(network, test_data, model_dir=logger.model_dir)

        print("\nGaude! Consummatum est.\n\n")


if __name__ == '__main__':
    import argparse

    strategies = ["cmap", "semlc", "adaptive-semlc", "parametric-semlc", "singleshot-semlc"]

    parser = argparse.ArgumentParser(usage='\nEXAMPLE: \n$ run.py CLC frozen\n\noptionally do HP optimisation '
                                           'using hp_params.json \n(index 23 in this example)\n'
                                           '$ run.py CLC frozen -p 23\n\noptionally overwrite default params\n'
                                           '$ run.py CLC frozen -c 3 -s 1,3,5 -w 2,3,4 -d 0.5,0.2,0.3\n')
    parser.add_argument("network", type=str, choices=AVAILABLE_NETWORKS)
    parser.add_argument("strategy", type=str, choices=strategies)
    parser.add_argument("--data", type=str, default="cifar10", choices=["cifar10", "mnist"], help="dataset to use")
    parser.add_argument("-w", "--widths", dest="widths", type=str, help="overwrite default widths", default=3)
    parser.add_argument("-d", "--damps", dest="damps", type=str, help="overwrite default damps", default=0.2)
    parser.add_argument("-c", "--cov", dest="coverage", type=int, help="coverage, default=1", default=1)
    parser.add_argument("-e", "--epochs", type=int, default=180, help="Number of epochs per model.")
    parser.add_argument("--init-std", type=float, help="std for weight initialization")

    parser.add_argument("-i", type=int, default=1, help="the number of iterations, default=1")
    parser.add_argument("-p", "--hpopt", type=str, help="hp optimisation with given index")
    parser.add_argument("--group", type=str, default=None, help="A group identifier, just for organizing.")
    parser.add_argument("--auto-group", action="store_true", help="Construct group name automatically based on parameters.")
    parser.add_argument("--force-device", type=str, choices=["cuda", "gpu", "cpu"])

    run(parser.parse_args())
