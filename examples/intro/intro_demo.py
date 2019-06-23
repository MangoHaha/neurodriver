#!/usr/bin/env python

"""
Introductory Neurokernel demo

Notes
-----
Generate input files and LPU configurations by running

cd data
python gen_generic_lpu.py -s 0 -l lpu_0 generic_lpu_0.gexf.gz generic_lpu_0_input.h5
python gen_generic_lpu.py -s 1 -l lpu_1 generic_lpu_1.gexf.gz generic_lpu_1_input.h5

Other seed values may be specified, but note that some may result in a network
that generates no meaningful responses to the input signal.
"""

import argparse
import random

import neurokernel.core_gpu as core
import neurokernel.pattern as pattern
import neurokernel.plsel as plsel
from neurokernel.tools.logging import setup_logger

from neurokernel.LPU.InputProcessors.FileInputProcessor import FileInputProcessor
from neurokernel.LPU.LPU import LPU
from neurokernel.LPU.OutputProcessors.FileOutputProcessor import FileOutputProcessor


def main():

    def run(connected):
        """
        Set `connected` to True to connect the LPUs.
        """

        out_name = 'un' if not connected else 'co'
        man = core.Manager()

        lpu_file_0 = './data/generic_lpu_0.gexf.gz'
        lpu_file_1 = './data/generic_lpu_1.gexf.gz'
        comp_dict_0, conns_0 = LPU.lpu_parser(lpu_file_0)
        comp_dict_1, conns_1 = LPU.lpu_parser(lpu_file_1)

        fl_input_processor_0 = FileInputProcessor('./data/generic_lpu_0_input.h5')
        fl_output_processor_0 = FileOutputProcessor(
                    [('V',None),('spike_state',None)],
                    'generic_lpu_0_%s_output.h5' % out_name, sample_interval=1)

        lpu_0_id = 'lpu_0'
        man.add(LPU, lpu_0_id, dt, comp_dict_0, conns_0,
                    input_processors = [fl_input_processor_0],
                    output_processors = [fl_output_processor_0],
                    device=args.gpu_dev[0],
                    debug=args.debug, time_sync=args.time_sync)

        fl_input_processor_1 = FileInputProcessor('./data/generic_lpu_1_input.h5')
        fl_output_processor_1 = FileOutputProcessor(
                    [('V',None),('spike_state',None)],
                    'generic_lpu_1_%s_output.h5' % out_name, sample_interval=1)

        lpu_1_id = 'lpu_1'
        man.add(LPU, lpu_1_id, dt, comp_dict_1, conns_1,
                    input_processors = [fl_input_processor_1],
                    output_processors = [fl_output_processor_1],
                    device=args.gpu_dev[1],
                    debug=args.debug, time_sync=args.time_sync)

        # Create random connections between the input and output ports if the LPUs
        # are to be connected:
        if connected:

            # Find all output and input port selectors in each LPU:
            out_ports_spk_0 = plsel.Selector(
                            ','.join(LPU.extract_out_spk(comp_dict_0, 'id')[0]))
            out_ports_gpot_0 = plsel.Selector(
                            ','.join(LPU.extract_out_gpot(comp_dict_0, 'id')[0]))

            out_ports_spk_1 = plsel.Selector(
                            ','.join(LPU.extract_out_spk(comp_dict_1, 'id')[0]))
            out_ports_gpot_1 = plsel.Selector(
                            ','.join(LPU.extract_out_gpot(comp_dict_1, 'id')[0]))

            in_ports_spk_0 = plsel.Selector(
                            ','.join(LPU.extract_in_spk(comp_dict_0, 'id')[0]))
            in_ports_gpot_0 = plsel.Selector(
                            ','.join(LPU.extract_in_gpot(comp_dict_0, 'id')[0]))

            in_ports_spk_1 = plsel.Selector(
                            ','.join(LPU.extract_in_spk(comp_dict_1, 'id')[0]))
            in_ports_gpot_1 = plsel.Selector(
                            ','.join(LPU.extract_in_gpot(comp_dict_1, 'id')[0]))

            out_ports_0 = plsel.Selector.union(out_ports_spk_0, out_ports_gpot_0)
            out_ports_1 = plsel.Selector.union(out_ports_spk_1, out_ports_gpot_1)

            in_ports_0 = plsel.Selector.union(in_ports_spk_0, in_ports_gpot_0)
            in_ports_1 = plsel.Selector.union(in_ports_spk_1, in_ports_gpot_1)

            # Initialize a connectivity pattern between the two sets of port
            # selectors:
            pat = pattern.Pattern(plsel.Selector.union(out_ports_0, in_ports_0),
                                  plsel.Selector.union(out_ports_1, in_ports_1))

            # Create connections from the ports with identifiers matching the output
            # ports of one LPU to the ports with identifiers matching the input
            # ports of the other LPU:
            N_conn_spk_0_1 = min(len(out_ports_spk_0), len(in_ports_spk_1))
            N_conn_gpot_0_1 = min(len(out_ports_gpot_0), len(in_ports_gpot_1))
            for src, dest in zip(random.sample(out_ports_spk_0.identifiers,
                                               N_conn_spk_0_1),
                                 random.sample(in_ports_spk_1.identifiers,
                                               N_conn_spk_0_1)):
                pat[src, dest] = 1
                pat.interface[src, 'type'] = 'spike'
                pat.interface[dest, 'type'] = 'spike'
            for src, dest in zip(random.sample(out_ports_gpot_0.identifiers,
                                               N_conn_gpot_0_1),
                                 random.sample(in_ports_gpot_1.identifiers,
                                               N_conn_gpot_0_1)):
                pat[src, dest] = 1
                pat.interface[src, 'type'] = 'gpot'
                pat.interface[dest, 'type'] = 'gpot'

            man.connect(lpu_0_id, lpu_1_id, pat, 0, 1)

        man.spawn()
        man.start(steps=args.steps)
        man.wait()

    dt = 1e-4
    dur = 1.0
    steps = int(dur/dt)

    parser = argparse.ArgumentParser()
    parser.add_argument('--debug', default=False,
                        dest='debug', action='store_true',
                        help='Write connectivity structures and inter-LPU routed data in debug folder')
    parser.add_argument('-l', '--log', default='none', type=str,
                        help='Log output to screen [file, screen, both, or none; default:none]')
    parser.add_argument('-s', '--steps', default=steps, type=int,
                        help='Number of steps [default: %s]' % steps)
    parser.add_argument('-r', '--time_sync', default=False, action='store_true',
                        help='Time data reception throughput [default: False]')
    parser.add_argument('-g', '--gpu_dev', default=[0, 1], type=int, nargs='+',
                        help='GPU device numbers [default: 0 1]')
    parser.add_argument('-d', '--disconnect', default=False, action='store_true',
                        help='Run with disconnected LPUs [default: False]')
    args = parser.parse_args()

    file_name = None
    screen = False
    if args.log.lower() in ['file', 'both']:
        file_name = 'neurokernel.log'
    if args.log.lower() in ['screen', 'both']:
        screen = True
    logger = setup_logger(file_name=file_name, screen=screen)

    random.seed(0)
    c = not args.disconnect
    run(c)

if __name__=='__main__':
    main()
