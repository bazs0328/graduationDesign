import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import KnowledgeScopePicker from '../../src/components/context/KnowledgeScopePicker.vue'

describe('KnowledgeScopePicker', () => {
  it('shows doc selector only after kb is selected in kb-and-optional-doc mode', async () => {
    const wrapper = mount(KnowledgeScopePicker, {
      props: {
        kbId: '',
        docId: '',
        kbs: [{ id: 'kb-1', name: 'KB 1' }],
        docs: [{ id: 'doc-1', filename: 'A.txt' }],
        mode: 'kb-and-optional-doc',
      },
    })

    expect(wrapper.findAll('select')).toHaveLength(1)

    await wrapper.setProps({ kbId: 'kb-1' })
    expect(wrapper.findAll('select')).toHaveLength(2)
    expect(wrapper.text()).toContain('限定文档')
  })

  it('emits kb/doc updates and uses required placeholder in required-doc mode', async () => {
    const wrapper = mount(KnowledgeScopePicker, {
      props: {
        kbId: 'kb-1',
        docId: '',
        kbs: [{ id: 'kb-1', name: 'KB 1' }],
        docs: [{ id: 'doc-1', filename: 'A.txt' }],
        mode: 'kb-and-required-doc',
      },
    })

    const selects = wrapper.findAll('select')
    expect(selects).toHaveLength(2)
    expect(wrapper.html()).toContain('请选择文档')

    await selects[0].setValue('kb-1')
    await selects[1].setValue('doc-1')

    expect(wrapper.emitted('update:kbId')).toBeTruthy()
    expect(wrapper.emitted('update:docId')).toBeTruthy()
    expect(wrapper.emitted('update:docId').at(-1)).toEqual(['doc-1'])
  })
})

