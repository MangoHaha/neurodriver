
from collections import OrderedDict

import numpy as np

import pycuda.gpuarray as garray
from pycuda.tools import dtype_to_ctype
import pycuda.driver as cuda
from pycuda.compiler import SourceModule

from BaseAxonHillockModel import BaseAxonHillockModel

class Wilson(BaseAxonHillockModel):
    updates = ['spike_state', 'V']
    accesses = ['I']
    params = OrderedDict()
    states = OrderedDict([
        ('R', 0.088),
        ('V',-70.),
        ('Vprev1', 'V'), # same as V
        ('Vprev2', 'V')  # same as V
    ])
    max_dt = 1e-5
    cuda_src = """
# if (defined(USE_DOUBLE))
#    define FLOATTYPE double
#    define EXP exp
#    define POW pow
# else
#    define FLOATTYPE float
#    define EXP expf
#    define POW powf
# endif
#
# if (defined(USE_LONG_LONG))
#     define INTTYPE long long
# else
#     define INTTYPE int
# endif


__global__ void update(
    int num_comps,
    FLOATTYPE dt,
    int nsteps,
    FLOATTYPE *g_I,
    FLOATTYPE *g_R,
    FLOATTYPE *g_internalV,
    FLOATTYPE *g_internalVprev1,
    FLOATTYPE *g_internalVprev2,
    INTTYPE *g_spike_state,
    FLOATTYPE *g_V)
{
    int tid = threadIdx.x + blockIdx.x * blockDim.x;
    int total_threads = gridDim.x * blockDim.x;

    FLOATTYPE V, Vprev1, Vprev2, dV;
    FLOATTYPE R, R_infty, dR;
    FLOATTYPE I;
    INTTYPE spike;


    for (int i = tid; i < num_comps; i += total_threads) {
        spike = 0;
        I = g_I[i];
        V = g_internalV[i];
        Vprev1 = g_internalVprev1[i];
        Vprev2 = g_internalVprev2[i];
        R = g_R[i];

        for (int j = 0; j < nsteps; ++j) {

            R_infty = 0.0135*V+1.03;

            dR = R_infty/1.9 - R/1.9;
            dV = 1./0.8*(I - 1.0*(17.81+0.4771*V+0.003263*V*V)*(V-55.) - 26.*R*(V+92.));

            V += dt * dV;
            R += dt * dR;

            spike += (Vprev2<=Vprev1) && (Vprev1 >= V) && (Vprev1 > 20.);

            Vprev2 = Vprev1;
            Vprev1 = V;
        }

        g_V[i] = V;
        g_R[i] = R;
        g_internalV[i] = V;
        g_internalVprev1[i] = Vprev1;
        g_internalVprev2[i] = Vprev2;
        g_spike_state[i] = (spike > 0);
    }
}
"""

    def run_step(self, update_pointers, st=None):
        for k in self.inputs:
            self.sum_in_variable(k, self.inputs[k], st=st)

        self.update_func.prepared_async_call(
            self.update_func.grid, self.update_func.block, st,
            self.num_comps, 1000.*self.dt, self.steps,
            *[self.inputs[k].gpudata for k in self.accesses]+\
            [self.params_dict[k].gpudata for k in self.params]+\
            [self.states[k].gpudata for k in self.states]+\
            [update_pointers[k] for k in self.updates])

    def get_update_func(self):
        mod = SourceModule(self.cuda_src, options=self.compile_options)
        func = mod.get_function("update")
        func.prepare('i'+np.dtype(self.floattype).char+'i'+'P'*self.num_garray)
        func.block = (128,1,1)
        func.grid = (min(6 * cuda.Context.get_device().MULTIPROCESSOR_COUNT,
                         (self.num_comps-1) / 128 + 1), 1)
        return func



if __name__ == '__main__':
    import argparse
    import itertools
    import networkx as nx
    from neurokernel.tools.logging import setup_logger
    import neurokernel.core_gpu as core

    from neurokernel.LPU.LPU import LPU

    from neurokernel.LPU.InputProcessors.FileInputProcessor import FileInputProcessor
    from neurokernel.LPU.InputProcessors.StepInputProcessor import StepInputProcessor
    from neurokernel.LPU.OutputProcessors.FileOutputProcessor import FileOutputProcessor

    import neurokernel.mpi_relaunch

    dt = 1e-4
    dur = 0.4
    steps = int(dur/dt)

    parser = argparse.ArgumentParser()
    parser.add_argument('--debug', default=False,
                        dest='debug', action='store_true',
                        help='Write connectivity structures and inter-LPU routed data in debug folder')
    parser.add_argument('-l', '--log', default='none', type=str,
                        help='Log output to screen [file, screen, both, or none; default:none]')
    parser.add_argument('-s', '--steps', default=steps, type=int,
                        help='Number of steps [default: %s]' % steps)
    parser.add_argument('-g', '--gpu_dev', default=0, type=int,
                        help='GPU device number [default: 0]')
    args = parser.parse_args()

    file_name = None
    screen = False
    if args.log.lower() in ['file', 'both']:
        file_name = 'neurokernel.log'
    if args.log.lower() in ['screen', 'both']:
        screen = True
    logger = setup_logger(file_name=file_name, screen=screen)

    man = core.Manager()

    G = nx.MultiDiGraph()

    G.add_node('neuron0', {
               'class': 'Wilson',
               'name': 'Wilson',
               })

    comp_dict, conns = LPU.graph_to_dicts(G)

    fl_input_processor = StepInputProcessor('I', ['neuron0'], 40.0, 0.1, 0.3)
    fl_output_processor = FileOutputProcessor([('spike_state', None),('V', None)], 'new_output.h5', sample_interval=1)

    man.add(LPU, 'ge', dt, comp_dict, conns, cuda_verbose=True,
            device=args.gpu_dev, input_processors = [fl_input_processor],
            output_processors = [fl_output_processor], debug=args.debug)

    man.spawn()
    man.start(steps=args.steps)
    man.wait()

    # plot the result
    import h5py
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    f = h5py.File('new_output.h5')
    t = np.arange(0, args.steps)*dt

    plt.figure()
    plt.subplot(211)
    plt.plot(t,f['V'].values()[0])
    plt.xlabel('time, [s]')
    plt.ylabel('Voltage, [mV]')
    plt.title('Wilson Neuron')
    plt.xlim([0, dur])
    # plt.ylim([-70, 60])
    plt.grid()
    plt.subplot(212)
    spk = f['spike_state/data'].value.flatten().nonzero()[0]
    plt.stem(t[spk],np.ones((len(spk),)))
    plt.xlabel('time, [s]')
    plt.ylabel('Spike')
    plt.xlim([0, dur])
    plt.ylim([0, 1.2])
    plt.grid()
    plt.tight_layout()
    plt.savefig('wilson.png',dpi=300)
