CREATE TABLE `anagrammer` (
    `word` VARCHAR(50) NOT NULL
    ,`alphagram` VARCHAR(50) NOT NULL
    ,`length` INT NOT NULL
    ,`a_ct` INT NOT NULL
    ,`b_ct` INT NOT NULL
    ,`c_ct` INT NOT NULL
    ,`d_ct` INT NOT NULL
    ,`e_ct` INT NOT NULL
    ,`f_ct` INT NOT NULL
    ,`g_ct` INT NOT NULL
    ,`h_ct` INT NOT NULL
    ,`i_ct` INT NOT NULL
    ,`j_ct` INT NOT NULL
    ,`k_ct` INT NOT NULL
    ,`l_ct` INT NOT NULL
    ,`m_ct` INT NOT NULL
    ,`n_ct` INT NOT NULL
    ,`o_ct` INT NOT NULL
    ,`p_ct` INT NOT NULL
    ,`q_ct` INT NOT NULL
    ,`r_ct` INT NOT NULL
    ,`s_ct` INT NOT NULL
    ,`t_ct` INT NOT NULL
    ,`u_ct` INT NOT NULL
    ,`v_ct` INT NOT NULL
    ,`w_ct` INT NOT NULL
    ,`x_ct` INT NOT NULL
    ,`y_ct` INT NOT NULL
    ,`z_ct` INT NOT NULL
    ,`score` INT NOT NULL
    ,PRIMARY KEY (`word`)
    ,INDEX `ix_alphagram`(`alphagram`)
    ,INDEX `ix_len`(`length`)
    ,INDEX `ix_a`(`a_ct`)
    ,INDEX `ix_b`(`b_ct`)
    ,INDEX `ix_c`(`c_ct`)
    ,INDEX `ix_d`(`d_ct`)
    ,INDEX `ix_e`(`e_ct`)
    ,INDEX `ix_f`(`f_ct`)
    ,INDEX `ix_g`(`g_ct`)
    ,INDEX `ix_h`(`h_ct`)
    ,INDEX `ix_i`(`i_ct`)
    ,INDEX `ix_j`(`j_ct`)
    ,INDEX `ix_k`(`k_ct`)
    ,INDEX `ix_l`(`l_ct`)
    ,INDEX `ix_m`(`m_ct`)
    ,INDEX `ix_n`(`n_ct`)
    ,INDEX `ix_o`(`o_ct`)
    ,INDEX `ix_p`(`p_ct`)
    ,INDEX `ix_q`(`q_ct`)
    ,INDEX `ix_r`(`r_ct`)
    ,INDEX `ix_s`(`s_ct`)
    ,INDEX `ix_t`(`t_ct`)
    ,INDEX `ix_u`(`u_ct`)
    ,INDEX `ix_v`(`v_ct`)
    ,INDEX `ix_w`(`w_ct`)
    ,INDEX `ix_x`(`x_ct`)
    ,INDEX `ix_y`(`y_ct`)
    ,INDEX `ix_z`(`z_ct`)
    );
